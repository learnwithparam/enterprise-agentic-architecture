"""HTTP API for the console. Every write names the acting user; Cedar decides what they may do.

uv run uvicorn hcpagents.api:app --port 8765
"""

import json
from functools import cache

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hcpagents import agents, authz, cases, events, graph, hcp360, infra, ledger, observe, store, world
from hcpagents.aws import client

app = FastAPI(title="Medical information platform")
DIST = world.ROOT / "web" / "dist"
EVAL_REPORT = world.ROOT / "evals" / "report.json"


@cache
def _pool() -> str:
    return client("ssm").get_parameter(Name="/mi/cognito/pool")["Parameter"]["Value"]


def user(x_user: str | None) -> dict:
    """The acting user, read from Cognito. Production takes this from a verified JWT instead of a header."""
    if not x_user:
        raise HTTPException(401, "Name the acting user in the X-User header")
    try:
        u = client("cognito-idp").admin_get_user(UserPoolId=_pool(), Username=x_user)
    except Exception as e:
        raise HTTPException(401, "Unknown user") from e
    a = {x["Name"]: x["Value"] for x in u["UserAttributes"]}
    p = world.person(u["Username"])
    return {"id": u["Username"], "name": a["name"], "role": a["custom:role"], "country": a["custom:country"], "title": p["title"]}


@app.middleware("http")
async def known_user_on_every_api_call(request: Request, call_next):
    """No /api route answers without a user Cognito knows, so a missing header never falls back to anyone."""
    if request.url.path.startswith("/api/"):
        try:
            user(request.headers.get("x-user"))
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    return await call_next(request)


def _denied(e: cases.Denied):
    raise HTTPException(403, str(e))


@app.get("/api/session")
def session(x_user: str | None = Header(None)):
    return {"user": user(x_user), "mode": "live" if agents.live() else "replay", "model": agents.MODEL, "today": world.TODAY.isoformat()}


@app.get("/api/meta")
def meta():
    return {"people": world.people(), "products": world.products()["product"], "countries": world.products()["country"],
            "company": world.products()["company"], "routes": list(world.ROUTES)}


def _visible(d: dict, u: dict) -> dict:
    ok, why = authz.user_can(u, "ViewCaseDetail", "Case", d["id"], {"country": d["country"], "route": d["route"]})
    if ok:
        return d
    keep = ("id", "route", "status", "country", "product", "created_at")
    return {k: d.get(k) for k in keep} | {"redacted": why, "inquiry": {"id": d["id"], "channel": d["inquiry"]["channel"]}}


@app.get("/api/inquiries")
def inquiries(x_user: str | None = Header(None)):
    u = user(x_user)
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
async def run_inquiry(inquiry_id: str, x_user: str | None = Header(None)):
    u = user(x_user)
    if world.inquiry(inquiry_id) is None:
        raise HTTPException(404, "No such inquiry")
    try:
        d = await cases.run(inquiry_id)
    except agents.MissingRecording as e:
        raise HTTPException(409, str(e)) from e
    except (agents.BudgetError, agents.ModelPolicyError) as e:
        raise HTTPException(402, str(e)) from e
    return _visible(d, u)


class Custom(BaseModel):
    hcp: str
    channel: str = "portal"
    text: str


@app.post("/api/inquiries")
async def custom_inquiry(body: Custom, x_user: str | None = Header(None)):
    """A question typed in the console. Needs LIVE=1 because nothing is recorded for it."""
    u = user(x_user)
    if not agents.live():
        raise HTTPException(409, "Typed questions call the model. Restart the server with LIVE=1 to allow it.")
    n = len([c for c in store.scan("mi-cases") if c["id"].startswith("custom-")]) + 1
    inq = {"id": f"custom-{n}", "channel": body.channel, "hcp": body.hcp, "received": cases._now(), "text": body.text[:2000],
           "expect": None}
    try:
        d = await cases.run(inq["id"], inq)
    except (agents.BudgetError, agents.ModelPolicyError) as e:
        raise HTTPException(402, str(e)) from e
    return _visible(d, u)


@app.get("/api/cases")
def list_cases(x_user: str | None = Header(None)):
    u = user(x_user)
    return [_visible(c, u) for c in sorted(store.scan("mi-cases"), key=lambda c: c["id"])]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, x_user: str | None = Header(None)):
    u = user(x_user)
    d = store.get("mi-cases", case_id)
    if d is None:
        raise HTTPException(404, "No such case. Run the inquiry first.")
    d = _visible(d, u)
    if "redacted" not in d:
        d["ledger"] = [r | {"entry": r["entry"]} for r in ledger.entries(case_id)]
        d["content_now"] = {s["block_id"]: _block_state(s["block_id"]) for s in (d.get("draft") or {}).get("segments", [])}
    return d


def _block_state(block_id: str) -> dict:
    b = store.get("mi-content", block_id)
    return {"version": b["version"], "status": b["status"], "current": world.is_current(b), "why_not": world.why_not_current(b)}


class Decision(BaseModel):
    note: str = ""


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, x_user: str | None = Header(None)):
    try:
        return cases.approve(case_id, user(x_user))
    except cases.Denied as e:
        _denied(e)


@app.post("/api/cases/{case_id}/reject")
def reject(case_id: str, body: Decision, x_user: str | None = Header(None)):
    try:
        return cases.reject(case_id, user(x_user), body.note or "No reason given")
    except cases.Denied as e:
        _denied(e)


@app.get("/api/content")
def content():
    out = []
    for b in sorted(store.content().values(), key=lambda b: (b["product"], b["country"], b["id"])):
        out.append(b | {"current": world.is_current(b), "why_not": world.why_not_current(b)})
    return out


@app.post("/api/content/{block_id}/withdraw")
def withdraw(block_id: str, body: Decision, x_user: str | None = Header(None)):
    if store.get("mi-content", block_id) is None:
        raise HTTPException(404, "No such block")
    try:
        return cases.withdraw(block_id, user(x_user), body.note or "Withdrawn by content owner")
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


class Autonomy(BaseModel):
    country: str
    enabled: bool


@app.get("/api/autonomy")
def autonomy():
    return {c["code"]: cases.autonomy_setting(c["code"]) for c in world.products()["country"]}


@app.post("/api/autonomy")
def set_autonomy(body: Autonomy, x_user: str | None = Header(None)):
    try:
        return cases.set_autonomy(body.country, body.enabled, user(x_user))
    except cases.Denied as e:
        _denied(e)


def _compliance(x_user: str | None) -> dict:
    u = user(x_user)
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
def tamper(x_user: str | None = Header(None)):
    u = _compliance(x_user)
    rows = ledger.entries()
    target = next((r for r in rows if r["entry"].get("type") == "routed" and r["entry"].get("route") != "send"), None)
    if target is None:
        raise HTTPException(409, "Run a case that is not sent automatically first")
    t = ledger.tamper(target["seq"])
    return {"tampered": t, "by": u["name"], "verify": ledger.verify()}


@app.post("/api/proof/restore")
def restore(x_user: str | None = Header(None)):
    _compliance(x_user)
    v = ledger.verify()
    if not v["ok"]:
        ledger.restore(v["broken_at"])
    return ledger.verify()


@app.post("/api/proof/delete-archive")
def delete_archive(x_user: str | None = Header(None)):
    _compliance(x_user)
    return ledger.try_delete_archive(1)


@app.get("/api/architecture")
def architecture():
    return {"routing": [{"fact": f, "value": v, "route": r, "why": w} for f, v, r, w in graph.ROUTING],
            "send": {"route": graph.SEND[0], "why": graph.SEND[1]},
            "nodes": [{"node": n, "facts": list(f)} for n, f in graph.NODES],
            "asl": graph.asl(), "model": agents.MODEL, "prompt_version": agents.PROMPT_VERSION,
            "agents": {k: {"system": v["system"], "tools": bool(v.get("tools")), "max_turns": v["max_turns"]} for k, v in agents.AGENTS.items()},
            "cedar": {f.name: f.read_text() for f in sorted((world.ROOT / "policies" / "cedar").glob("*.cedar"))}}


@app.post("/api/reset")
def reset(x_user: str | None = Header(None)):
    u = user(x_user)
    ok, why = authz.user_can(u, "ResetDemo", "Ledger", "main", {})
    if not ok:
        raise HTTPException(403, f"{u['name']} may not reset the platform. {why}")
    infra.provision(reset=True)
    authz._store.cache_clear()
    authz._policy_file.cache_clear()
    return {"ok": True}


if DIST.exists():
    app.mount("/_astro", StaticFiles(directory=DIST / "_astro"), name="astro") if (DIST / "_astro").exists() else None
    app.mount("/fonts", StaticFiles(directory=DIST / "fonts"), name="fonts") if (DIST / "fonts").exists() else None

    @app.get("/{page:path}")
    def page(page: str):
        f = DIST / page / "index.html" if not page.endswith(".html") else DIST / page
        if not f.exists():
            f = DIST / f"{page}.html" if (DIST / f"{page}.html").exists() else DIST / "index.html"
        if not f.resolve().is_relative_to(DIST.resolve()):
            raise HTTPException(404)
        return FileResponse(f)
