"""The machine interfaces: /v1 and /mcp are token gated, tenant scoped, rate limited and Cedar checked (ADR 0028)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, cache, cases, infra, ratelimit
from tests.test_flow import as_user

pytestmark = pytest.mark.floci

MCP = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)
    for k in cache._client().scan_iter("rl:*"):  # counters outlive a run, so start every test with empty windows
        cache._client().delete(k)


@pytest.fixture(scope="module")
def client():
    """One app lifespan for the module, which keeps the 44 s of worker start-up out of every test."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("MI_WORKER", "off")
        with TestClient(api.app, base_url="http://localhost:8765") as c:
            yield c


def call_tool(client, headers, name, args=None):
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    client.post("/mcp/", json=init, headers=MCP | headers)
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}
    return client.post("/mcp/", json=body, headers=MCP | headers).json()


def test_every_machine_route_needs_a_token(client):
    for path in ("/v1/cases", "/v1/releases", "/v1/dead-letters", "/mcp/"):
        assert client.get(path).status_code == 401, path
    assert client.post("/mcp/", json={}, headers=MCP).status_code == 401


def test_v1_lists_cases_for_the_callers_tenant_only(client):
    asyncio.run(cases.run("inq-101"))
    mine = client.get("/v1/cases", headers=as_user("u-brandt")).json()
    assert any(c["id"] == "inq-101" for c in mine)
    assert client.get("/v1/cases", headers=as_user("u-reyes")).json() == []
    assert client.get("/v1/cases/inq-101", headers=as_user("u-reyes")).status_code == 404


def test_v1_redacts_a_case_for_a_field_rep(client):
    asyncio.run(cases.run("inq-101"))
    d = client.get("/v1/cases/inq-101", headers=as_user("u-becker")).json()
    assert "redacted" in d and "draft" not in d


def test_a_user_over_the_limit_is_told_to_wait(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "LIMIT", 2)
    h = as_user("u-lind")
    codes = [client.get("/v1/cases", headers=h).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and codes[-1] == 429
    r = client.get("/v1/cases", headers=h)
    assert int(r.headers["Retry-After"]) > 0
    assert client.get("/v1/cases", headers=as_user("u-tanaka")).status_code == 200


def test_the_case_stream_ends_with_its_status(client):
    asyncio.run(cases.run("inq-101"))
    r = client.get("/v1/cases/inq-101/events?max_s=3", headers=as_user("u-brandt"))
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "event: history" in r.text and r.text.rstrip().endswith('"status": "sent"}')


def test_only_compliance_replays_a_parked_event_or_promotes(client):
    for user, code in (("u-brandt", 403), ("u-raman", 404)):
        h = as_user(user)
        assert client.post("/v1/dead-letters/999999/replay", headers=h).status_code == code
    assert client.post("/v1/releases/r-none/promote", headers=as_user("u-brandt")).status_code == 403
    assert client.post("/v1/releases/r-none/promote", headers=as_user("u-raman")).status_code == 409


def test_v1_shows_a_release_diff_and_a_missing_one_is_404(client):
    assert client.get("/v1/releases/diff?a=r-x&b=r-y", headers=as_user("u-raman")).status_code == 404
    assert isinstance(client.get("/v1/releases", headers=as_user("u-raman")).json(), list)


def test_mcp_tools_are_tenant_scoped_and_cedar_checked(client):
    asyncio.run(cases.run("inq-101"))
    ok = call_tool(client, as_user("u-brandt"), "list_cases")
    assert "inq-101" in [c["id"] for c in ok["result"]["structuredContent"]["result"]]
    other = call_tool(client, as_user("u-reyes"), "get_case", {"case_id": "inq-101"})
    assert other["result"]["isError"]
    sensitive = call_tool(client, as_user("u-brandt"), "release_trend")
    assert sensitive["result"]["isError"] and "may not call release_trend" in sensitive["result"]["content"][0]["text"]
    assert not call_tool(client, as_user("u-raman"), "release_trend")["result"].get("isError")
    assert call_tool(client, as_user("u-becker"), "list_cases")["result"]["isError"]
