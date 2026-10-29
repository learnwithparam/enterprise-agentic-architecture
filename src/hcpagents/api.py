"""HTTP API for the console. Every write names the acting user; Cedar decides what they may do.

uv run uvicorn hcpagents.api:app --port 8765
"""

import contextlib
import json
import os
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hcpagents import agents, auth, authz, aws, cases, db, durable, events, gateway, graph, guardian, hcp360, improver, infra, ingest, insight, ledger, mcp_server, observe, outreach, ratelimit, releases, store, v1, world

@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """Dev runs the Temporal worker inside the API; in production MI_WORKER=off and `hcpagents.worker` is its own deployable."""
    with gateway.for_live_calls():
        server = mcp_server.build()
        mcp_server.mount.current = server.streamable_http_app()
        async with server.session_manager.run():
            if os.environ.get("MI_WORKER", "embedded") == "off":
                yield
                return
            client = await durable.connect()
            async with durable.worker(client):
                await durable.start_steward(client)
                await durable.ensure_schedules(client)
                yield


app = FastAPI(title="Medical information platform", lifespan=lifespan)
DIST = world.ROOT / "web" / "dist"
EVAL_REPORT = world.ROOT / "evals" / "report.json"


PUBLIC = {"/api/login", "/api/login-options", "/api/health"}
PROTECTED = ("/api/", "/v1/", "/mcp")
MACHINE = ("/v1/", "/mcp")


class Login(BaseModel):
    user: str
    password: str


def current_user(request: Request) -> dict:
    """The verified user the middleware attached to this request."""
    return request.state.user


@app.middleware("http")
async def verified_token_on_every_api_call(request: Request, call_next):
    """No /api, /v1 or /mcp route answers without a signed token, and the caller's tenant scopes every query they run."""
    path = request.url.path
    if path.startswith(PROTECTED) and path not in PUBLIC:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        try:
            if scheme.lower() != "bearer" or not token:
                raise auth.Unauthenticated("Send the ID token as Authorization: Bearer")
            request.state.user = auth.verify(token)
        except auth.Unauthenticated as e:
            return JSONResponse({"detail": str(e)}, status_code=401)
        if path.startswith(MACHINE) and (wait := ratelimit.hit(request.state.user["tenant"], request.state.user["id"])):
            return JSONResponse({"detail": "Rate limit reached"}, status_code=429, headers={"Retry-After": str(wait)})
        with db.as_tenant(request.state.user["tenant"]):
            return await call_next(request)
    return await call_next(request)


@app.post("/hooks/{tenant}/{channel}", status_code=202)
async def channel_webhook(tenant: str, channel: str, request: Request):
    """A channel reports an event. No token here: the HMAC signature over the body is the credential."""
    if tenant not in {t["id"] for t in world.tenants()}:
        raise HTTPException(404, "No such tenant")
    body = await request.body()
    try:
        ingest.verify(tenant, channel, request.headers.get("x-mi-timestamp", ""), request.headers.get("x-mi-signature", ""), body)
        return ingest.accept(tenant, channel, json.loads(body), via="webhook")
    except ingest.Rejected as e:
        raise HTTPException(e.status, str(e)) from e
    except json.JSONDecodeError as e:
        raise HTTPException(422, "The body is not JSON") from e


@app.post("/api/login")
def login(body: Login):
    try:
        return {"token": auth.login(body.user, body.password)}
    except auth.Unauthenticated as e:
        raise HTTPException(401, str(e)) from e


def _denied(e: cases.Denied):
    raise HTTPException(403, str(e))


@app.get("/api/login-options")
def login_options():
    """Who can sign in, for the demo sign-in screen: names and roles only, never a credential.

    Only against the local emulator. A real deployment lists nobody, so the screen asks for a user id and
    the endpoint cannot be used to enumerate accounts.
    """
    if not aws.ENDPOINT:
        return {"tenants": [], "people": []}
    return {"tenants": world.tenants(),
            "people": [{k: u.get(k) for k in ("id", "name", "role", "country", "title")} | {"tenant": u.get("tenant", world.DEFAULT_TENANT)}
                       for u in world.directory()]}


@app.get("/api/health")
def health():
    """The load balancer's liveness probe. It says nothing about the data and needs no token."""
    return {"status": "ok"}


@app.get("/api/session")
def session(u: dict = Depends(current_user)):
    return {"user": u, "mode": "live" if agents.live() else "replay", "model": agents.MODEL, "today": world.TODAY.isoformat()}


@app.get("/api/meta")
def meta():
    return {"people": world.people(), "products": world.products()["product"], "countries": world.products()["country"],
            "company": world.products()["company"], "routes": list(world.ROUTES)}


@app.get("/api/inquiries")
def inquiries(u: dict = Depends(current_user)):
    done = {c["id"]: c for c in store.scan("mi-cases")}
    out = []
    for i in world.inquiries():
        if not i.get("inbox") and i["id"] not in done:
            continue
        h = world.hcp(i.get("hcp"))
        c = done.get(i["id"])
        submitter = (i.get("submitted_by") or "").split(",")[0]
        can_read, _ = authz.user_can(u, "ViewInquiryText", "Inquiry", i["id"], {"submitter": submitter})
        out.append({"id": i["id"], "channel": i["channel"], "received": i["received"], "text": i["text"] if can_read else None,
                    "from": h["name"] if h else i.get("sender"), "country": h["country"] if h else i.get("country"),
                    "submitted_by": i.get("submitted_by"), "eval_only": not i.get("inbox"),
                    "case": c and {"route": c["route"], "status": c["status"], "product": c["product"]}})
    return out


@app.post("/api/inquiries/{inquiry_id}/run")
async def run_inquiry(inquiry_id: str, u: dict = Depends(current_user)):
    if world.inquiry(inquiry_id) is None:
        raise HTTPException(404, "No such inquiry")
    try:
        d = await durable.run_inquiry(inquiry_id)
    except agents.MissingRecording as e:
        raise HTTPException(409, str(e)) from e
    except (agents.BudgetError, agents.ModelPolicyError) as e:
        raise HTTPException(402, str(e)) from e
    return cases.visible(d, u)


class Custom(BaseModel):
    hcp: str
    channel: str = "portal"
    text: str


@app.post("/api/inquiries")
async def custom_inquiry(body: Custom, u: dict = Depends(current_user)):
    """A question typed in the console. Needs LIVE=1 because nothing is recorded for it."""
    if not agents.live():
        raise HTTPException(409, "Typed questions call the model. Restart the server with LIVE=1 to allow it.")
    n = len([c for c in store.scan("mi-cases") if c["id"].startswith("custom-")]) + 1
    inq = {"id": f"custom-{n}", "channel": body.channel, "hcp": body.hcp, "received": cases._now(), "text": body.text[:2000],
           "expect": None}
    try:
        d = await durable.run_inquiry(inq["id"], inq)
    except (agents.BudgetError, agents.ModelPolicyError) as e:
        raise HTTPException(402, str(e)) from e
    return cases.visible(d, u)


@app.get("/api/cases")
def list_cases(u: dict = Depends(current_user)):
    return [cases.visible(c, u) for c in sorted(store.scan("mi-cases"), key=lambda c: c["id"])]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, u: dict = Depends(current_user)):
    d = store.get("mi-cases", case_id)
    if d is None:
        raise HTTPException(404, "No such case. Run the inquiry first.")
    d = cases.visible(d, u)
    if "redacted" not in d:
        d["ledger"] = [r | {"entry": r["entry"]} for r in ledger.entries(case_id, reveal=True)]
        d["content_now"] = {s["block_id"]: _block_state(s["block_id"]) for s in (d.get("draft") or {}).get("segments", [])}
    return d


def _block_state(block_id: str) -> dict:
    b = store.get("mi-content", block_id)
    return {"version": b["version"], "status": b["status"], "current": world.is_current(b), "why_not": world.why_not_current(b)}


class Decision(BaseModel):
    note: str = ""


class Signoff(BaseModel):
    password: str


@app.post("/api/cases/{case_id}/approve")
async def approve(case_id: str, body: Signoff, u: dict = Depends(current_user)):
    """The approver re-enters their password; that sign-in is their signature on the approval."""
    try:
        signature = auth.reauthenticate(u, body.password)
    except auth.Unauthenticated as e:
        raise HTTPException(403, str(e)) from e
    try:
        return await durable.decide(case_id, u, "approve", signature=signature)
    except cases.Denied as e:
        _denied(e)


@app.post("/api/cases/{case_id}/reject")
async def reject(case_id: str, body: Decision, u: dict = Depends(current_user)):
    try:
        return await durable.decide(case_id, u, "reject", note=body.note or "No reason given")
    except cases.Denied as e:
        _denied(e)


@app.get("/api/content")
def content():
    out = []
    for b in sorted(store.content().values(), key=lambda b: (b["product"], b["country"], b["id"])):
        out.append(b | {"current": world.is_current(b), "why_not": world.why_not_current(b)})
    return out


@app.post("/api/content/{block_id}/withdraw")
def withdraw(block_id: str, body: Decision, u: dict = Depends(current_user)):
    if store.get("mi-content", block_id) is None:
        raise HTTPException(404, "No such block")
    try:
        return cases.withdraw(block_id, u, body.note or "Withdrawn by content owner")  # the steward re-checks the drafts
    except cases.Denied as e:
        _denied(e)


@app.get("/api/hcps")
def hcps():
    return hcp360.summary()


@app.get("/api/hcps/{hcp_id}")
def hcp(hcp_id: str):
    if store.get("mi-hcp", hcp_id) is None:
        raise HTTPException(404, "No such HCP")
    return hcp360.view(hcp_id)


@app.get("/api/insights")
def insights(since: datetime | None = None):
    return insight.digest(since)


@app.get("/api/releases")
def release_trend():
    return releases.trend(world.current_tenant())


@app.get("/api/monitors")
def monitors():
    """What live cases did under each release, to compare a canary with the baseline."""
    return releases.online(world.current_tenant())


@app.get("/api/hcps/{hcp_id}/outreach")
def hcp_outreach(hcp_id: str):
    if store.get("mi-hcp", hcp_id) is None:
        raise HTTPException(404, "No such HCP")
    return outreach.coordinate(hcp_id)


class Autonomy(BaseModel):
    country: str
    enabled: bool


@app.get("/api/autonomy")
def autonomy():
    return {c["code"]: cases.autonomy_setting(c["code"]) for c in world.products()["country"]}


@app.post("/api/autonomy")
def set_autonomy(body: Autonomy, u: dict = Depends(current_user)):
    try:
        return cases.set_autonomy(body.country, body.enabled, u)
    except cases.Denied as e:
        _denied(e)


def _compliance(u: dict) -> dict:
    ok, why = authz.user_can(u, "AuditLedger", "Ledger", "main", {})
    if not ok:
        raise HTTPException(403, f"{u['name']} may not run ledger checks. {why}")
    return u


@app.get("/api/proof")
def proof():
    rows = ledger.entries()
    report = json.loads(EVAL_REPORT.read_text()) if EVAL_REPORT.exists() else None
    cs = store.scan("mi-cases")
    return {
        "ledger": ledger.verify(), "recent": rows[-40:][::-1], "evals": report,
        "routes": observe.route_counts(), "queues": events.depth(),
        "spend": {"cases": len(cs), "cost_usd": round(sum(c.get("cost_usd", 0) for c in cs), 6),
                  "live_cases": sum(c.get("mode") == "live" for c in cs)},
    }


@app.post("/api/proof/tamper")
def tamper(u: dict = Depends(current_user)):
    _compliance(u)
    rows = ledger.entries()
    target = next((r for r in rows if r["entry"].get("type") == "routed" and r["entry"].get("route") != "send"), None)
    if target is None:
        raise HTTPException(409, "Run a case that is not sent automatically first")
    t = ledger.tamper(target["seq"])
    return {"tampered": t, "by": u["name"], "verify": ledger.verify()}


@app.post("/api/proof/restore")
def restore(u: dict = Depends(current_user)):
    _compliance(u)
    v = ledger.verify()
    if not v["ok"]:
        ledger.restore(v["broken_at"])
    return ledger.verify()


@app.post("/api/proof/delete-archive")
def delete_archive(u: dict = Depends(current_user)):
    _compliance(u)
    return ledger.try_delete_archive(1)


@app.post("/api/hcps/{hcp_id}/erase")
def erase_hcp(hcp_id: str, u: dict = Depends(current_user)):
    try:
        return cases.erase_person(hcp_id, u)
    except cases.Denied as e:
        _denied(e)


@app.get("/api/architecture")
def architecture():
    return {"routing": [{"fact": f, "value": v, "route": r, "why": w} for f, v, r, w in graph.ROUTING],
            "send": {"route": graph.SEND[0], "why": graph.SEND[1]},
            "nodes": [{"node": n, "facts": list(f)} for n, f in graph.NODES],
            "asl": graph.asl(), "model": agents.MODEL, "prompt_version": agents.PROMPT_VERSION,
            "agents": {k: {"system": v["system"], "tools": bool(v.get("tools")), "max_turns": v["max_turns"]} for k, v in agents.AGENTS.items()},
            "cedar": {f.name: f.read_text() for f in sorted((world.ROOT / "policies" / "cedar").glob("*.cedar"))}}


@app.post("/api/reset")
def reset(u: dict = Depends(current_user)):
    ok, why = authz.user_can(u, "ResetDemo", "Ledger", "main", {})
    if not ok:
        raise HTTPException(403, f"{u['name']} may not reset the platform. {why}")
    infra.provision(reset=True)
    authz._store.cache_clear()
    authz._policy_file.cache_clear()
    return {"ok": True}


@app.get("/api/agents")
def agents_page():
    """The roster with what each agent has cost this tenant, and the autonomy every country has granted."""
    spend = {r["agent"]: r for r in gateway.spend_by(world.current_tenant(), "agent")}
    return {"agents": [a | {"calls": int(spend[a["id"]]["calls"]) if a["id"] in spend else 0,
                            "cost_usd": float(spend[a["id"]]["cost_usd"]) if a["id"] in spend else 0.0} for a in world.agents()],
            "autonomy": {c["code"]: cases.autonomy_setting(c["code"]) for c in world.products()["country"]},
            "guardian": guardian.override_rates(), "proposals": proposals()}


@app.get("/api/guardian")
def guardian_status():
    return guardian.override_rates()


@app.get("/api/proposals")
def proposals():
    return [d for d in store.scan("mi-proposals") if d["kind"] != "correction"]


@app.post("/api/proposals/refresh")
def refresh_proposals():
    return improver.propose()


app.include_router(v1.router)
app.mount("/mcp", mcp_server.mount)

if DIST.exists():
    app.mount("/_next", StaticFiles(directory=DIST / "_next"), name="next") if (DIST / "_next").exists() else None
    app.mount("/fonts", StaticFiles(directory=DIST / "fonts"), name="fonts") if (DIST / "fonts").exists() else None

    # HEAD too: the console's links prefetch their pages with it
    @app.api_route("/{page:path}", methods=["GET", "HEAD"])
    def page(page: str):
        f = DIST / page / "index.html" if not page.endswith(".html") else DIST / page
        if not f.exists():
            f = DIST / f"{page}.html" if (DIST / f"{page}.html").exists() else DIST / "index.html"
        if not f.resolve().is_relative_to(DIST.resolve()):
            raise HTTPException(404)
        return FileResponse(f)

