"""The platform as MCP tools, so a client's own agents can read cases and release metrics (ADR 0028).

Mounted at /mcp over streamable HTTP. The API middleware has already verified the bearer token, applied
the tenant and charged the rate limit by the time a tool runs. Each tool then asks Cedar whether this
user may call it, so a tool is a policy decision and not only a function.
"""

import os

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from hcpagents import authz, cases, db, releases, store

TOOLS = {"list_cases": "no", "get_case": "no", "release_trend": "yes"}  # name -> sensitive


class ToolDenied(Exception):
    pass


def _user(ctx: Context, tool: str) -> dict:
    u = ctx.request_context.request.state.user
    ok, why = authz.user_can(u, "CallMcpTool", "Tool", tool, {"sensitive": TOOLS[tool]})
    if not ok:
        raise ToolDenied(f"{u['id']} may not call {tool}. {why}")
    return u


def list_cases(ctx: Context) -> list[dict]:
    """Every case in the caller's tenant, redacted to what the caller may see."""
    u = _user(ctx, "list_cases")
    with db.as_tenant(u["tenant"]):
        return [cases.visible(c, u) for c in sorted(store.scan("mi-cases"), key=lambda c: c["id"])]


def get_case(case_id: str, ctx: Context) -> dict:
    """One case with its route, draft and status."""
    u = _user(ctx, "get_case")
    with db.as_tenant(u["tenant"]):
        d = store.get("mi-cases", case_id)
    if d is None:
        raise LookupError(f"No such case {case_id}")
    return cases.visible(d, u)


def release_trend(ctx: Context) -> list[dict]:
    """Eval metrics, cost and spend per release. Compliance only."""
    u = _user(ctx, "release_trend")
    return releases.trend(u["tenant"])


# The MCP SDK refuses any Host it was not told about (DNS rebinding). Production lists its domain in MI_MCP_HOSTS.
HOSTS = ["localhost:*", "127.0.0.1:*", *filter(None, os.environ.get("MI_MCP_HOSTS", "").split(","))]


def build() -> FastMCP:
    """A fresh server. Its session manager can run once, so every app lifespan builds its own."""
    server = FastMCP("hcp-platform", stateless_http=True, json_response=True, streamable_http_path="/",
                     transport_security=TransportSecuritySettings(allowed_hosts=HOSTS, allowed_origins=["*"]))
    for tool in (list_cases, get_case, release_trend):
        server.tool()(tool)
    return server


class Mount:
    """What /mcp points at: the MCP app of the lifespan that is running now."""
    current = None

    async def __call__(self, scope, receive, send):
        await self.current(scope, receive, send)


mount = Mount()
