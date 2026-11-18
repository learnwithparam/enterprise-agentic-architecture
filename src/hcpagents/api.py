"""HTTP API for the console. Every write names the acting user, and Cedar decides what they may do.

The console routes live in the api_*.py modules. This file holds the app, the token check and the pages.

uv run uvicorn hcpagents.api:app --port 8765
"""

import base64
import contextlib
import hashlib
import json
import os
import re
from functools import cache
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hcpagents import api_agents, api_cases, api_check, api_config, api_content, api_outreach, api_proof, auth, aws, db, durable, gateway, ingest, mcp_server, ratelimit, v1, world


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """Dev runs the Temporal worker inside the API. In production MI_WORKER is off and the worker runs alone."""
    with gateway.for_live_calls():
        server = mcp_server.build()
        mcp_server.mount.current = server.streamable_http_app()
        async with server.session_manager.run():
            if os.environ.get("MI_WORKER", "embedded") == "off":
                yield
                return
            client = await durable.connect()
            async with durable.workers(client):
                await durable.start_steward(client)
                await durable.ensure_schedules(client)
                yield


app = FastAPI(title="Medical information platform", lifespan=lifespan)
DIST = world.ROOT / "web" / "dist"


PUBLIC = {"/api/login", "/api/login-options", "/api/health", "/api/config"}
PROTECTED = ("/api/", "/v1/", "/mcp")
MACHINE = ("/v1/", "/mcp")


class Login(BaseModel):
    user: str
    password: str
    mfa_code: str | None = None


@app.middleware("http")
async def verified_token_on_every_api_call(request: Request, call_next):
    """Every /api, /v1 and /mcp route needs a signed token. The caller's tenant limits each query."""
    path = request.url.path
    if path.startswith(PROTECTED) and path not in PUBLIC:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        try:
            if scheme.lower() != "bearer" or not token:
                raise auth.Unauthenticated("Send the ID token as Authorization: Bearer")
            request.state.user = auth.verify(token)
        except auth.Unauthenticated as error:
            challenge = f'Bearer resource_metadata="{request.base_url}.well-known/oauth-protected-resource"'
            return JSONResponse({"detail": str(error)}, status_code=401, headers={"WWW-Authenticate": challenge})
        except auth.WrongTenant as error:
            return JSONResponse({"detail": str(error)}, status_code=403)
        if path.startswith(MACHINE):
            wait = ratelimit.hit(request.state.user["tenant"], request.state.user["id"])
            if wait:
                return JSONResponse({"detail": "Rate limit reached"}, status_code=429, headers={"Retry-After": str(wait)})
        with db.as_tenant(request.state.user["tenant"]):
            return await call_next(request)
    return await call_next(request)


@app.post("/hooks/{tenant}/{channel}", status_code=202, dependencies=[Depends(ratelimit.HOOKS)])
async def channel_webhook(tenant: str, channel: str, request: Request):
    """A channel reports an event. There is no token here. The HMAC signature over the body is the credential."""
    if tenant not in {entry["id"] for entry in world.tenants()}:
        raise HTTPException(404, "No such tenant")
    body = await request.body()
    try:
        ingest.verify(tenant, channel, request.headers.get("x-mi-timestamp", ""), request.headers.get("x-mi-signature", ""), body)
        return ingest.accept(tenant, channel, json.loads(body), via="webhook")
    except ingest.Rejected as error:
        raise HTTPException(error.status, str(error)) from error
    except json.JSONDecodeError as error:
        raise HTTPException(422, "The body is not JSON") from error


@app.post("/api/login", dependencies=[Depends(ratelimit.LOGIN)])
def login(body: Login):
    try:
        return {"token": auth.login(body.user, body.password, body.mfa_code)}
    except auth.Unauthenticated as error:
        raise HTTPException(401, str(error)) from error


def _person_row(person: dict) -> dict:
    row = {key: person.get(key) for key in ("id", "name", "role", "country", "title")}
    return row | {"tenant": person.get("tenant", world.DEFAULT_TENANT)}


@app.get("/api/login-options")
def login_options():
    """Who can sign in, for the demo sign-in screen. It shows names and roles, never a credential.

    This works only against the local emulator. A real deployment lists nobody.
    So the screen asks for a user id, and nobody can use the endpoint to list accounts.
    """
    if not aws.ENDPOINT:
        return {"tenants": [], "people": []}
    return {"cli_client_id": auth.cli_client_id(), "tenants": world.tenants(),
            "people": [_person_row(person) for person in world.directory()]}


@app.get("/.well-known/oauth-protected-resource")
def protected_resource(request: Request):
    """RFC 9728 says which issuer signs the tokens this API takes. An MCP client or the CLI finds the sign-in from it."""
    return {"resource": f"{request.base_url}mcp", "authorization_servers": [auth.issuer()],
            "bearer_methods_supported": ["header"], "scopes_supported": ["openid"]}


@app.get("/api/health")
def health():
    """The load balancer's liveness probe. It says nothing about the data and needs no token."""
    return {"status": "ok"}


CONSOLE = ratelimit.SlidingWindow(int(os.environ.get("MI_API_PER_MIN", "120")))


def console_limit(request: Request) -> None:
    """Each signed in user gets a budget of console calls per minute. A noisy user cannot slow the others."""
    user = getattr(request.state, "user", None)
    key = ratelimit.caller_address(request)
    if user:
        key = f"{user['tenant']}:{user['id']}"
    wait = CONSOLE.hit(key)
    if wait:
        raise HTTPException(429, "Too many requests", headers={"Retry-After": str(wait)})


def add_routes(router: APIRouter) -> None:
    """Put a route module's routes straight on the app, so each shows up in `app.routes`. Console routes get the limit."""
    for route in router.routes:
        guards = []
        if route.path.startswith("/api/"):
            guards = [Depends(console_limit)]
        app.add_api_route(route.path, route.endpoint, methods=sorted(route.methods), dependencies=guards)


for routes in (api_cases.router, api_check.router, api_config.router, api_content.router, api_outreach.router, *api_proof.routers(), api_agents.router):
    add_routes(routes)
app.include_router(v1.router)
app.mount("/mcp", mcp_server.mount)


@cache
def _inline_script_hashes(file: Path, mtime: float) -> tuple[str, ...]:
    html = file.read_text()
    bodies = re.findall(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", html, re.S)
    hashes = []
    for body in bodies:
        if body.strip():
            hashes.append(f"'sha256-{base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()}'")
    return tuple(hashes)


def content_security_policy(file: Path) -> str:
    """The console is a static export, so the policy is set here.

    Scripts run from this origin, plus the inline start scripts of the page, by hash. Nothing else runs.
    So an injected script tag does not run. Styles allow inline because React writes style attributes.
    """
    scripts = " ".join(("'self'", *_inline_script_hashes(file, file.stat().st_mtime)))
    connect = "'self'"
    if not aws.is_local():
        connect += f" https://cognito-idp.{aws.REGION}.amazonaws.com"
    return (f"default-src 'self'; script-src {scripts}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            f"font-src 'self'; connect-src {connect}; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


if DIST.exists():
    for folder, name in (("_next", "next"), ("fonts", "fonts")):
        if (DIST / folder).exists():
            app.mount(f"/{folder}", StaticFiles(directory=DIST / folder), name=name)


def _page_file(page: str) -> Path:
    if page.endswith(".html"):
        found = DIST / page
    else:
        found = DIST / page / "index.html"
    if not found.exists():
        found = DIST / "index.html"
        if (DIST / f"{page}.html").exists():
            found = DIST / f"{page}.html"
    return found


# HEAD too, because the console links fetch pages with it. It is added last, so API routes win.
@app.api_route("/{page:path}", methods=["GET", "HEAD"])
def page(page: str):
    found = _page_file(page)
    if not found.resolve().is_relative_to(DIST.resolve()) or not found.exists():
        raise HTTPException(404)
    headers = None
    if found.suffix == ".html":
        headers = {"Content-Security-Policy": content_security_policy(found)}
    return FileResponse(found, headers=headers)
