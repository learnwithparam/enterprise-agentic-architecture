"""The platform as MCP tools, so a client's own agents can read cases and release metrics (ADR 0028).

It is mounted at /mcp over streamable HTTP. The API middleware has already checked the bearer token.
It has also set the tenant and charged the rate limit by the time a tool runs.
Each tool then asks Cedar if this user may call it. So a tool is a policy decision, not only a function.
"""

import hashlib
import inspect
import json
import os
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from hcpagents import authz, cases, db, releases, store

TOOLS = {"list_cases": "no", "get_case": "no", "release_trend": "yes"}  # name -> sensitive


PIN_FILE = Path(__file__).with_name("mcp_pins.json")
DISABLED: list[str] = []  # tools left out at start because their description no longer matches its pin


class ToolDenied(Exception):
    pass


def description_hash(tool) -> str:
    """The fingerprint of a tool: its name and the description a client's model reads."""
    return hashlib.sha256(f"{tool.__name__}\n{inspect.getdoc(tool)}".encode()).hexdigest()


def pinned(tools: tuple, pins: dict) -> list:
    """The tools whose description is as it was pinned. The rest are named in DISABLED and never served."""
    # Step 1: Forget the tools left out last time.
    DISABLED.clear()
    served = []
    for tool in tools:
        # Step 2: A tool that matches its pin is served.
        if pins.get(tool.__name__) == description_hash(tool):
            served.append(tool)
        # Step 3: Name a changed tool and skip it.
        else:
            DISABLED.append(tool.__name__)
    return served


def _by_id(case: dict) -> str:
    return case["id"]


def _user(context: Context, tool: str) -> dict:
    user = context.request_context.request.state.user
    allowed, reason = authz.user_can(user, "CallMcpTool", "McpTool", tool, {"sensitive": TOOLS[tool]})
    if not allowed:
        raise ToolDenied(f"{user['id']} may not call {tool}. {reason}")
    return user


def list_cases(context: Context) -> list[dict]:
    """Every case in the caller's tenant, cut down to what the caller may see."""
    user = _user(context, "list_cases")
    with db.as_tenant(user["tenant"]):
        return [cases.visible(case, user) for case in sorted(store.scan("mi-cases"), key=_by_id)]


def get_case(case_id: str, context: Context) -> dict:
    """One case with its route, draft and status."""
    user = _user(context, "get_case")
    with db.as_tenant(user["tenant"]):
        case = store.get("mi-cases", case_id)
    if case is None:
        raise LookupError(f"No such case {case_id}")
    return cases.visible(case, user)


def release_trend(context: Context) -> list[dict]:
    """Eval metrics, cost and spend per release. Compliance only."""
    user = _user(context, "release_trend")
    return releases.trend(user["tenant"])


# The MCP SDK refuses any host it was not told about.
# Production lists its own domain in MI_MCP_HOSTS.
HOSTS = ["localhost:*", "127.0.0.1:*", *filter(None, os.environ.get("MI_MCP_HOSTS", "").split(","))]


def build() -> FastMCP:
    """A fresh server. Its session manager runs once, so each app lifespan builds one."""
    server = FastMCP("hcp-platform", stateless_http=True, json_response=True, streamable_http_path="/",
                     transport_security=TransportSecuritySettings(allowed_hosts=HOSTS, allowed_origins=["*"]))
    pins = json.loads(PIN_FILE.read_text())
    for tool in pinned((list_cases, get_case, release_trend), pins):
        server.tool()(tool)
    return server


class Mount:
    """What /mcp points at. It is the MCP app of the lifespan that runs now."""
    current = None

    async def __call__(self, scope, receive, send):
        await self.current(scope, receive, send)


mount = Mount()


if __name__ == "__main__":
    # Run this once a person has read a changed description.
    reviewed = (list_cases, get_case, release_trend)
    PIN_FILE.write_text(json.dumps({tool.__name__: description_hash(tool) for tool in reviewed}, indent=2) + "\n")
