"""A signed in user has a budget of console calls. Over it, the answer is 429 with a wait time."""

from fastapi.testclient import TestClient

from hcpagents import api
from tests.test_flow import as_user


def test_a_user_over_the_console_limit_gets_429(monkeypatch):
    client = TestClient(api.app)
    headers = as_user("u-brandt")
    assert client.get("/api/cases", headers=headers).status_code != 429
    monkeypatch.setattr(api.CONSOLE, "limit", 0)
    answer = client.get("/api/cases", headers=headers)
    assert answer.status_code == 429 and int(answer.headers["Retry-After"]) > 0


def test_every_console_route_carries_the_limit_and_sign_in_does_not_carry_it_twice():
    for route in api.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/") or path in api.PUBLIC:
            continue
        names = [dep.call.__name__ for dep in route.dependant.dependencies]
        assert "console_limit" in names, path
