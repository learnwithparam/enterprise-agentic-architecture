"""Every model call goes through the gateway: a virtual key, the allowlist, a budget, failover, and a tagged spend row (ADR 0019)."""

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from hcpagents import agents, db, gateway, infra, world

pytestmark = pytest.mark.floci

HAIKU, SONNET = agents.HAIKU, agents.SONNET
USAGE = {"input_tokens": 1000, "output_tokens": 200}
HEADERS = {"x-mi-case": "inq-101", "x-mi-release": "r7", "x-mi-prompt-version": "p3"}


def provider(status: int = 200, stream: bool = False) -> tuple[FastAPI, list]:
    """A stand-in for the model provider that answers with `status` and counts what it was asked."""
    fake, seen = FastAPI(), []

    @fake.post("/v1/messages")
    async def messages(request: Request):
        seen.append({"key": request.headers["x-api-key"], "body": await request.json()})
        if status != 200:
            return JSONResponse({"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}, status_code=status)
        if not stream:
            return {"id": "m1", "content": [{"type": "text", "text": "ok"}], "usage": USAGE}

        async def events():
            yield f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": {"usage": {"input_tokens": 1000, "output_tokens": 1}}})}\n\n'
            yield f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "usage": {"output_tokens": 200}})}\n\n'
        return StreamingResponse(events(), media_type="text/event-stream")
    return fake, seen


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


class Gateway:
    """The gateway under test, with stand-in providers behind it."""

    def __init__(self, apps):
        self.upstreams = [gateway.Upstream(f"up{i}", "http://provider", f"real-key-{i}", httpx.ASGITransport(app=a)) for i, a in enumerate(apps)]

    def post(self, key: str, payload: dict, headers: dict | None = None):
        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app), base_url="http://gw") as gw:
                return await gw.post("/v1/messages", json=payload, headers={"x-api-key": key} | (HEADERS if headers is None else headers))
        return asyncio.run(go())


@pytest.fixture
def via(monkeypatch):
    def use(*apps: FastAPI) -> Gateway:
        g = Gateway(apps)
        monkeypatch.setattr(gateway, "upstreams", lambda: g.upstreams)
        return g
    return use


def body(model: str = HAIKU, **kw) -> dict:
    return {"model": model, "max_tokens": 50, "messages": [{"role": "user", "content": "hi"}]} | kw


def spend(key: str) -> list[dict]:
    """The spend rows one key produced; the log is never wiped, so each test reads only its own."""
    with world.as_tenant("quillon"), db.session() as conn:
        return conn.execute("SELECT * FROM spend_log WHERE key_hash = %s ORDER BY id", (gateway._hash(key),)).fetchall()


def test_a_call_is_forwarded_with_the_provider_key_and_logged_with_its_tags(via):
    fake, seen = provider()
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = via(fake).post(key, body())
    assert r.status_code == 200 and seen[0]["key"] == "real-key-0" and key not in json.dumps(seen)
    [row] = spend(key)
    assert (row["tenant_id"], row["agent"], row["release"], row["prompt_version"], row["case_id"], row["model"]) == \
           ("quillon", "triage", "r7", "p3", "inq-101", HAIKU)
    assert float(row["cost_usd"]) == agents.cost_usd(USAGE, HAIKU) > 0


def test_a_streamed_call_is_priced_from_its_events(via):
    fake, _ = provider(stream=True)
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = via(fake).post(key, body(stream=True))
    assert r.status_code == 200 and "message_delta" in r.text
    assert float(spend(key)[0]["cost_usd"]) == agents.cost_usd(USAGE, HAIKU)


def test_a_model_outside_the_allowlist_is_refused_before_the_provider_hears_of_it(via):
    fake, seen = provider()
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = via(fake).post(key, body("claude-opus-5-5"))
    assert r.status_code == 400 and not seen and not spend(key)


def test_a_call_without_a_valid_key_is_refused(via):
    fake, seen = provider()
    gw = via(fake)
    key = gateway.issue_key("quillon", "triage", 1.0)
    assert (gw.post("sk-ant-the-real-provider-key", body())).status_code == 401
    assert (gw.post(key[:-1] + "x", body())).status_code == 401
    gateway.revoke("quillon", key)
    assert (gw.post(key, body())).status_code == 401 and not seen


def test_a_key_over_its_budget_is_refused(via):
    fake, seen = provider()
    gw = via(fake)
    key = gateway.issue_key("quillon", "triage", agents.cost_usd(USAGE, HAIKU) * 1.5)
    assert (gw.post(key, body())).status_code == 200
    assert (gw.post(key, body())).status_code == 200  # still under budget before this call's cost lands
    assert (gw.post(key, body())).status_code == 429 and len(seen) == 2


def test_a_key_works_only_inside_its_own_tenant(via):
    fake, _ = provider()
    gw = via(fake)
    key = gateway.issue_key("quillon", "triage", 1.0)
    forged = key.replace("vk.quillon.", "vk.marlowe.", 1)
    assert (gw.post(forged, body())).status_code == 401


def test_a_key_issued_in_another_tenant_is_proved_inside_that_tenant(via):
    fake, _ = provider()
    gw = via(fake)
    key = gateway.issue_key("marlowe", "triage", 1.0)
    assert gw.post(key, body()).status_code == 200
    assert gateway.resolve(key)["tenant"] == "marlowe"


def test_when_the_first_provider_is_busy_the_next_one_answers_and_the_log_says_which(via):
    busy, _ = provider(status=529)
    good, seen = provider()
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = via(busy, good).post(key, body())
    assert r.status_code == 200 and r.headers["x-mi-upstream"] == "up1" and seen
    assert spend(key)[0]["upstream"] == "up1"


def test_when_every_provider_fails_the_caller_gets_a_502_and_the_failure_is_logged(via):
    busy, _ = provider(status=503)
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = via(busy).post(key, body())
    assert r.status_code == 502 and spend(key)[0]["status"] == 502


def test_spend_splits_by_release_and_prompt_version(via):
    fake, _ = provider()
    gw = via(fake)
    key = gateway.issue_key("quillon", "triage", 1.0)
    gw.post(key, body())
    gw.post(key, body(SONNET), {"x-mi-release": "r8", "x-mi-prompt-version": "p4"})
    by = {(r["release"], r["prompt_version"]): float(r["cost_usd"]) for r in spend(key)}
    assert by == {("r7", "p3"): agents.cost_usd(USAGE, HAIKU), ("r8", "p4"): agents.cost_usd(USAGE, SONNET)}
    assert {"release", "prompt_version", "cost_usd"} <= set(gateway.spend_by("quillon", "release", "prompt_version")[0])


def test_a_live_agent_call_carries_a_virtual_key_and_the_gateway_url_never_the_provider_key(monkeypatch):
    monkeypatch.setenv("MI_GATEWAY", "http://gw:8766")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-the-real-provider-key")
    env = agents._options(HAIKU, "triage", {"id": "inq-101"}, {}, None, lambda *_: None, []).env
    assert env["ANTHROPIC_BASE_URL"] == "http://gw:8766" and env["ANTHROPIC_API_KEY"].startswith("vk.quillon.triage.")
    assert "x-mi-case: inq-101" in env["ANTHROPIC_CUSTOM_HEADERS"] and agents.PROMPT_VERSION in env["ANTHROPIC_CUSTOM_HEADERS"]
    monkeypatch.delenv("MI_GATEWAY")
    with pytest.raises(RuntimeError, match="AI gateway"):
        agents._options(HAIKU, "triage", {"id": "inq-101"}, {}, None, lambda *_: None, [])
