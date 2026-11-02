"""Every model call goes through the gateway: a virtual key, the allowlist, a budget, failover, and a tagged spend row (ADR 0019)."""

import asyncio
import json

import httpx
import pytest
from botocore.exceptions import ClientError
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
    tampered = key[:-1] + ("y" if key[-1] == "x" else "x")  # always differs, whatever the random last character is
    assert (gw.post(tampered, body())).status_code == 401
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


# ---------------------------------------------------------------- Amazon Bedrock as the second provider (ADR 0019)

class Bedrock:
    """A bedrock-runtime client that records what it was asked and answers, or fails, as told."""

    def __init__(self, fail: Exception | None = None):
        self.calls, self.fail = [], fail

    def converse(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return {"output": {"message": {"role": "assistant", "content": [{"text": "from bedrock"}]}}, "stopReason": "end_turn",
                "usage": {"inputTokens": 1000, "outputTokens": 200}}


class TimedOut(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise httpx.ReadTimeout("the provider did not answer", request=request)


def bedrock_second(monkeypatch, first: httpx.AsyncBaseTransport | FastAPI, bedrock: Bedrock) -> None:
    transport = first if isinstance(first, httpx.AsyncBaseTransport) else httpx.ASGITransport(app=first)
    monkeypatch.setattr(gateway, "upstreams", lambda: [
        gateway.Upstream("anthropic", "http://provider", "real-key", transport),
        gateway.Upstream("bedrock", "", "", kind="bedrock", client=bedrock)])


def throttled() -> ClientError:
    return ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}, "ResponseMetadata": {"HTTPStatusCode": 429}}, "Converse")


def call(key: str, payload: dict | None = None):
    return Gateway([]).post(key, payload or body())


def test_primary_503_fails_over(monkeypatch):
    busy, _ = provider(status=503)
    br = Bedrock()
    bedrock_second(monkeypatch, busy, br)
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = call(key)
    assert r.status_code == 200 and r.json()["content"][0]["text"] == "from bedrock" and len(br.calls) == 1


def test_429_fails_over(monkeypatch):
    limited, _ = provider(status=429)
    br = Bedrock()
    bedrock_second(monkeypatch, limited, br)
    assert call(gateway.issue_key("quillon", "triage", 1.0)).status_code == 200 and br.calls


def test_timeout_fails_over(monkeypatch):
    br = Bedrock()
    bedrock_second(monkeypatch, TimedOut(), br)
    assert call(gateway.issue_key("quillon", "triage", 1.0)).status_code == 200 and br.calls


def test_a_throttled_bedrock_is_the_last_stop_and_the_caller_gets_a_502(monkeypatch):
    busy, _ = provider(status=503)
    bedrock_second(monkeypatch, busy, Bedrock(fail=throttled()))
    key = gateway.issue_key("quillon", "triage", 1.0)
    assert call(key).status_code == 502 and spend(key)[0]["status"] == 502


def test_provider_recorded_and_metered(monkeypatch):
    good, seen = provider()
    busy, _ = provider(status=503)
    key = gateway.issue_key("quillon", "triage", 1.0)
    bedrock_second(monkeypatch, good, Bedrock())
    first = call(key)
    bedrock_second(monkeypatch, busy, Bedrock())
    second = call(key)
    assert (first.headers["x-mi-upstream"], second.headers["x-mi-upstream"]) == ("anthropic", "bedrock")
    rows = spend(key)
    assert [r["upstream"] for r in rows] == ["anthropic", "bedrock"]
    assert [float(r["cost_usd"]) for r in rows] == [agents.cost_usd(USAGE, HAIKU)] * 2 and seen


def test_converse_translation_roundtrip():
    request = {"model": SONNET, "max_tokens": 300, "temperature": 0.2, "system": [{"type": "text", "text": "Be brief."}],
               "messages": [{"role": "user", "content": "hi"},
                            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "x"}}]},
                            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "found"}]}],
               "tools": [{"name": "lookup", "description": "Find it", "input_schema": {"type": "object"}}],
               "tool_choice": {"type": "tool", "name": "lookup"}}
    out = gateway.to_converse(request, SONNET)
    assert out["modelId"] == gateway.BEDROCK_MODELS[SONNET] and out["system"] == [{"text": "Be brief."}]
    assert out["inferenceConfig"] == {"maxTokens": 300, "temperature": 0.2}
    assert out["messages"][1]["content"] == [{"toolUse": {"toolUseId": "t1", "name": "lookup", "input": {"q": "x"}}}]
    assert out["messages"][2]["content"][0]["toolResult"] == {"toolUseId": "t1", "content": [{"text": "found"}], "status": "success"}
    assert out["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"] == {"json": {"type": "object"}}
    assert out["toolConfig"]["toolChoice"] == {"tool": {"name": "lookup"}}
    back = gateway.from_converse({"output": {"message": {"content": [{"text": "ok"}, {"toolUse": {"toolUseId": "t2", "name": "lookup", "input": {"q": "y"}}}]}},
                                  "stopReason": "tool_use", "usage": {"inputTokens": 7, "outputTokens": 3}}, SONNET)
    assert back["content"] == [{"type": "text", "text": "ok"}, {"type": "tool_use", "id": "t2", "name": "lookup", "input": {"q": "y"}}]
    assert (back["stop_reason"], back["usage"]) == ("tool_use", {"input_tokens": 7, "output_tokens": 3})


def test_a_streaming_caller_gets_events_it_can_price(monkeypatch):
    busy, _ = provider(status=503)
    bedrock_second(monkeypatch, busy, Bedrock())
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = call(key, body(stream=True))
    assert r.status_code == 200 and "content_block_delta" in r.text and "message_stop" in r.text
    assert float(spend(key)[0]["cost_usd"]) == agents.cost_usd(USAGE, HAIKU)


def test_the_real_bedrock_wire_answers_through_the_emulator(monkeypatch):
    """No fake client here: boto3 calls Floci's bedrock-runtime. Its reply is a stub, so this proves the wire, not the words."""
    busy, _ = provider(status=503)
    bedrock_second(monkeypatch, busy, None)
    key = gateway.issue_key("quillon", "triage", 1.0)
    r = call(key)
    assert r.status_code == 200 and r.json()["content"][0]["text"].startswith(f"Floci stub response for model=anthropic.{HAIKU}")
    assert spend(key)[0]["upstream"] == "bedrock"


def test_bedrock_joins_the_chain_only_when_a_region_is_set(monkeypatch):
    monkeypatch.delenv("MI_BEDROCK_REGION", raising=False)
    assert [u.name for u in gateway.upstreams()] == ["anthropic"]
    monkeypatch.setenv("MI_BEDROCK_REGION", "eu-central-1")
    assert [u.name for u in gateway.upstreams()] == ["anthropic", "bedrock"]
