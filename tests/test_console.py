"""The console and the API cannot drift apart: every path a page calls is a route, every nav link a page."""

import re
from pathlib import Path

from hcpagents import api, v1, world

WEB = Path(__file__).resolve().parents[1] / "web"
CALL = re.compile(r"""(?:api|useApi|stream|useEventStream)\(\s*[`'"](/(?:api|v1)/[^`'"?]*)""")


def route_patterns() -> list[re.Pattern]:
    paths = [r.path for r in api.app.routes if hasattr(r, "path")] + [r.path for r in v1.router.routes]
    return [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$") for p in paths]


def console_calls() -> set[str]:
    calls = set()
    for f in [*WEB.glob("app/**/*.jsx"), *WEB.glob("components/*.jsx"), *WEB.glob("lib/*.js")]:
        for m in CALL.finditer(f.read_text()):
            calls.add(re.sub(r"\$\{[^}]+\}", "x", m.group(1)).rstrip("/"))
    return calls


def test_every_path_the_console_calls_is_a_route():
    calls, routes = console_calls(), route_patterns()
    assert len(calls) >= 15
    # a call whose last segment is a variable (the proof actions) needs a route under the same parent
    missing = sorted(c for c in calls if not any(r.match(c) or (c.endswith("/x") and r.pattern.startswith("^" + c[:-1])) for r in routes))
    assert not missing, missing


def test_every_nav_link_has_a_page():
    shell = (WEB / "components/Shell.jsx").read_text()
    hrefs = re.findall(r"\['[^']+', '(/[a-z0-9]*)'\]", shell)
    assert len(hrefs) == 8
    for href in hrefs:
        page = WEB / "app" / href.strip("/") / "page.jsx"
        assert page.exists(), page


def test_every_agent_in_the_roster_is_a_model_the_router_may_pick_or_none():
    models = {a["model"] for a in world.agents()}
    assert models <= {"haiku", "sonnet", "none"}


def test_every_page_answers_the_prefetch_a_link_sends():
    from fastapi.testclient import TestClient

    if not api.DIST.exists():
        return
    client = TestClient(api.app)
    for href in ("/", "/inbox", "/agents", "/releases", "/proof"):
        assert client.head(href).status_code == 200, href


def test_a_real_deployment_lists_nobody_on_the_sign_in_screen(monkeypatch):
    assert api.login_options()["people"], "the local emulator lists the demo personas"
    monkeypatch.setattr(api.aws, "ENDPOINT", "")
    assert api.login_options() == {"tenants": [], "people": []}
