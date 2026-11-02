"""The AI gateway: every model call passes through here (ADR 0019).

It speaks the Anthropic Messages API, so the Agent SDK points ANTHROPIC_BASE_URL at it and needs no other
change. An agent holds a virtual key (tenant + agent + budget), never the provider key. For each call the
gateway checks the key, the model allowlist and the key's budget, forwards to the first upstream that
answers, and writes one spend_log row tagged with tenant, agent, release, prompt version and case.

uv run uvicorn hcpagents.gateway:app --port 8766
"""

import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass

import boto3
import httpx
import uvicorn
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from hcpagents import aws, db, world
from hcpagents.agents import ALLOWED_MODELS, HAIKU, SONNET, cost_usd
from hcpagents.aws import client

PORT = 8766


def release() -> str:
    """The release this process runs: MI_RELEASE when set, else the hash of its manifest (ADR 0025)."""
    from hcpagents import releases  # lazy: releases reads agents and this module
    return os.environ.get("MI_RELEASE") or releases.current()


RETRY_STATUS = {429, 500, 502, 503, 504, 529}  # the provider is busy or down: try the next upstream
FORWARD = ("content-type", "anthropic-version", "anthropic-beta")
USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


BEDROCK_MODELS = {m: f"anthropic.{m}-v1:0" for m in (HAIKU, SONNET)}  # derived, so the allowlist stays the only list of models
BEDROCK_STOP = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "max_tokens", "stop_sequence": "stop_sequence",
                "guardrail_intervened": "refusal", "content_filtered": "refusal"}


@dataclass
class Upstream:
    name: str
    base_url: str
    key: str
    transport: httpx.AsyncBaseTransport | None = None
    kind: str = "messages"  # "messages" speaks the Anthropic API; "bedrock" is translated to Converse
    client: object | None = None  # a bedrock-runtime client; built on first use when None


def upstreams() -> list[Upstream]:
    """Anthropic first. Then Amazon Bedrock when MI_BEDROCK_REGION is set (same models, same account boundary),
    then a second Anthropic-compatible endpoint (a proxy) when configured."""
    out = [Upstream("anthropic", "https://api.anthropic.com", os.environ.get("ANTHROPIC_API_KEY", ""))]
    if os.environ.get("MI_BEDROCK_REGION"):
        out.append(Upstream("bedrock", "", "", kind="bedrock"))
    if url := os.environ.get("MI_GATEWAY_FALLBACK_URL"):
        out.append(Upstream("fallback", url, os.environ.get("MI_GATEWAY_FALLBACK_KEY", "")))
    return out


class Refused(Exception):
    def __init__(self, status: int, kind: str, message: str):
        super().__init__(message)
        self.status, self.kind = status, kind


# ---------------------------------------------------------------- virtual keys

def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue_key(tenant: str, agent: str, budget_usd: float) -> str:
    """A new virtual key: vk.<tenant>.<agent>.<secret>. Only its hash is kept."""
    secret = f"vk.{tenant}.{agent}.{secrets.token_urlsafe(24)}"
    with world.as_tenant(tenant), db.session() as conn:
        conn.execute("INSERT INTO virtual_keys (tenant_id, key_hash, agent, budget_usd) VALUES (%s, %s, %s, %s)",
                     (tenant, _hash(secret), agent, budget_usd))
    return secret


def key_for(tenant: str, agent: str) -> str:
    """The key this tenant's agent uses. Kept in SSM so every process shares it; issued on first use."""
    name = f"/mi/gateway/{tenant}/{agent}"
    with contextlib.suppress(client("ssm").exceptions.ParameterNotFound):
        secret = client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        with world.as_tenant(tenant), db.session() as conn:
            if conn.execute("SELECT 1 FROM virtual_keys WHERE key_hash = %s AND NOT revoked", (_hash(secret),)).fetchone():
                return secret
    secret = issue_key(tenant, agent, world.autonomy_seed()["budget"]["per_session_usd"])
    client("ssm").put_parameter(Name=name, Value=secret, Type="SecureString", Overwrite=True)
    return secret


def revoke(tenant: str, secret: str) -> None:
    with world.as_tenant(tenant), db.session() as conn:
        conn.execute("UPDATE virtual_keys SET revoked = true WHERE key_hash = %s", (_hash(secret),))


def resolve(secret: str) -> dict:
    """The tenant, agent and budget a key stands for, or a refusal. The tenant is read from the key and
    then proved by the hash lookup inside that tenant, so a forged prefix finds nothing."""
    parts = secret.split(".", 3)
    if len(parts) != 4 or parts[0] != "vk":
        raise Refused(401, "authentication_error", "Send a gateway virtual key as x-api-key")
    tenant = parts[1]
    with world.as_tenant(tenant), db.session() as conn:
        row = conn.execute("SELECT agent, budget_usd, revoked FROM virtual_keys WHERE key_hash = %s", (_hash(secret),)).fetchone()
        if row is None or row["revoked"]:
            raise Refused(401, "authentication_error", "Unknown or revoked virtual key")
        spent = conn.execute("SELECT COALESCE(sum(cost_usd), 0) AS s FROM spend_log WHERE key_hash = %s", (_hash(secret),)).fetchone()["s"]
    return {"tenant": tenant, "agent": row["agent"], "hash": _hash(secret), "budget": float(row["budget_usd"]), "spent": float(spent)}


# ---------------------------------------------------------------- spend log

def record(vk: dict, meta: dict, model: str, upstream: str, status: int, usage: dict, latency_ms: int) -> None:
    cost = cost_usd(usage, model) if model in ALLOWED_MODELS else 0.0
    with world.as_tenant(vk["tenant"]), db.session() as conn:
        conn.execute(
            "INSERT INTO spend_log (tenant_id, key_hash, agent, release, prompt_version, case_id, model, upstream, status, "
            "input_tokens, output_tokens, cache_read, cache_write, cost_usd, latency_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (vk["tenant"], vk["hash"], vk["agent"], meta["release"], meta["prompt_version"], meta["case"], model, upstream, status,
             usage.get("input_tokens", 0), usage.get("output_tokens", 0), usage.get("cache_read_input_tokens", 0),
             usage.get("cache_creation_input_tokens", 0), cost, latency_ms))


def spend_by(tenant: str, *columns: str) -> list[dict]:
    """Cost for a tenant grouped by any of agent, release, prompt_version, model, case_id."""
    allowed = {"agent", "release", "prompt_version", "model", "case_id"}
    assert set(columns) <= allowed, columns
    cols = ", ".join(columns)
    with world.as_tenant(tenant), db.session() as conn:
        return conn.execute(f"SELECT {cols}, count(*) AS calls, sum(cost_usd) AS cost_usd FROM spend_log "
                            f"WHERE status < 400 GROUP BY {cols} ORDER BY {cols}").fetchall()


# ---------------------------------------------------------------- Amazon Bedrock

def _bedrock(up: Upstream):
    if up.client is None:
        if aws.ENDPOINT:
            up.client = client("bedrock-runtime")
        else:  # one attempt: failing over is the gateway's job, not the SDK's
            up.client = boto3.client("bedrock-runtime", region_name=os.environ["MI_BEDROCK_REGION"],
                                     config=Config(read_timeout=120, retries={"max_attempts": 1}))
    return up.client


def _text(content) -> list[dict]:
    return [{"text": content}] if isinstance(content, str) else [{"text": b["text"]} for b in content if b.get("type") == "text"]


def _block(b: dict) -> dict:
    if b["type"] == "text":
        return {"text": b["text"]}
    if b["type"] == "tool_use":
        return {"toolUse": {"toolUseId": b["id"], "name": b["name"], "input": b["input"]}}
    if b["type"] == "tool_result":
        return {"toolResult": {"toolUseId": b["tool_use_id"], "content": _text(b.get("content", "")),
                               "status": "error" if b.get("is_error") else "success"}}
    raise ValueError(f"Bedrock translation has no mapping for a {b['type']} block")


def to_converse(body: dict, model: str) -> dict:
    """A Messages API request as a Bedrock Converse request."""
    out: dict = {"modelId": BEDROCK_MODELS[model],
                 "messages": [{"role": m["role"], "content": [{"text": m["content"]}] if isinstance(m["content"], str)
                               else [_block(b) for b in m["content"]]} for m in body["messages"]],
                 "inferenceConfig": {"maxTokens": body["max_tokens"]}}
    if body.get("system"):
        out["system"] = _text(body["system"])
    for src, dst in (("temperature", "temperature"), ("top_p", "topP"), ("stop_sequences", "stopSequences")):
        if src in body:
            out["inferenceConfig"][dst] = body[src]
    if body.get("tools"):
        out["toolConfig"] = {"tools": [{"toolSpec": {"name": t["name"], "description": t.get("description", ""),
                                                      "inputSchema": {"json": t["input_schema"]}}} for t in body["tools"]]}
        choice = body.get("tool_choice", {}).get("type")
        if choice in ("any", "tool"):
            out["toolConfig"]["toolChoice"] = {"any": {}} if choice == "any" else {"tool": {"name": body["tool_choice"]["name"]}}
    return out


def from_converse(reply: dict, model: str) -> dict:
    """A Bedrock Converse reply as a Messages API message."""
    content = []
    for b in reply["output"]["message"]["content"]:
        if "text" in b:
            content.append({"type": "text", "text": b["text"]})
        elif "toolUse" in b:
            u = b["toolUse"]
            content.append({"type": "tool_use", "id": u["toolUseId"], "name": u["name"], "input": u["input"]})
    return {"id": f"msg_bedrock_{secrets.token_hex(8)}", "type": "message", "role": "assistant", "model": model, "content": content,
            "stop_reason": BEDROCK_STOP.get(reply["stopReason"], "end_turn"), "stop_sequence": None,
            "usage": {"input_tokens": reply["usage"]["inputTokens"], "output_tokens": reply["usage"]["outputTokens"]}}


def as_events(message: dict) -> bytes:
    """The Server-Sent Events a streaming caller expects, replayed from a finished message."""
    def ev(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps({'type': name} | data)}\n\n"
    out = [ev("message_start", {"message": message | {"content": [], "usage": {**message["usage"], "output_tokens": 1}}})]
    for i, b in enumerate(message["content"]):
        start = b | ({"text": ""} if b["type"] == "text" else {"input": {}})
        delta = {"type": "text_delta", "text": b["text"]} if b["type"] == "text" else {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}
        out += [ev("content_block_start", {"index": i, "content_block": start}), ev("content_block_delta", {"index": i, "delta": delta}),
                ev("content_block_stop", {"index": i})]
    out += [ev("message_delta", {"delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
                                 "usage": {"output_tokens": message["usage"]["output_tokens"]}}), ev("message_stop", {})]
    return "".join(out).encode()


def _error_response(status: int, kind: str, message: str) -> httpx.Response:
    return httpx.Response(status, json={"type": "error", "error": {"type": kind, "message": message}})


async def _converse(up: Upstream, body: dict, model: str) -> httpx.Response:
    """Call Bedrock and answer as the Messages API would. Throttling and 5xx come back as their status, so the
    same retry set moves on to the next upstream; a timeout or a lost connection raises like any transport error."""
    try:
        reply = await asyncio.to_thread(lambda: _bedrock(up).converse(**to_converse(body, model)))
    except ClientError as e:
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
        return _error_response(status, "api_error", e.response.get("Error", {}).get("Message", "Bedrock refused the call"))
    except BotoCoreError as e:
        raise httpx.TransportError(str(e)) from e
    message = from_converse(reply, model)
    if body.get("stream"):
        return httpx.Response(200, content=as_events(message), headers={"content-type": "text/event-stream"})
    return httpx.Response(200, json=message)


# ---------------------------------------------------------------- the proxy

app = FastAPI(title="AI gateway")


def _error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse({"type": "error", "error": {"type": kind, "message": message}}, status_code=status)


def _absorb(usage: dict, event: dict) -> None:
    if event.get("type") == "message_start":
        usage.update(event["message"].get("usage", {}))
    elif event.get("type") == "message_delta":
        usage.update(event.get("usage", {}))


def _usage(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if k in USAGE and isinstance(v, int)}


@app.post("/v1/messages")
async def messages(request: Request):
    started = time.perf_counter()
    secret = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        vk = resolve(secret)
    except Refused as e:
        return _error(e.status, e.kind, str(e))
    body = await request.json()
    model = body.get("model")
    if model not in ALLOWED_MODELS:
        return _error(400, "invalid_request_error", f"{model} is not allowed; use one of {sorted(ALLOWED_MODELS)}")
    if vk["spent"] >= vk["budget"]:
        return _error(429, "rate_limit_error", f"The {vk['agent']} key spent ${vk['spent']:.4f} of its ${vk['budget']:.2f} budget")
    meta = {"case": request.headers.get("x-mi-case", "-"), "release": request.headers.get("x-mi-release", release()),
            "prompt_version": request.headers.get("x-mi-prompt-version", "-")}
    headers = {k: v for k, v in request.headers.items() if k in FORWARD}
    payload = json.dumps(body).encode()

    last: Exception | None = None
    for up in upstreams():
        http = httpx.AsyncClient(transport=up.transport, base_url=up.base_url, timeout=120)
        try:
            if up.kind == "bedrock":
                resp = await _converse(up, body, model)
            else:
                resp = await http.send(http.build_request("POST", "/v1/messages", content=payload, headers=headers | {"x-api-key": up.key}),
                                       stream=True)
        except httpx.HTTPError as e:
            last = e
            await http.aclose()
            continue
        if resp.status_code in RETRY_STATUS:
            last = RuntimeError(f"{up.name} answered {resp.status_code}")
            await resp.aclose()
            await http.aclose()
            continue
        return await _relay(resp, http, up, vk, meta, model, started, bool(body.get("stream")))
    record(vk, meta, model, "none", 502, {}, round((time.perf_counter() - started) * 1000))
    return _error(502, "api_error", f"Every upstream failed; last: {last}")


async def _relay(resp: httpx.Response, http: httpx.AsyncClient, up: Upstream, vk: dict, meta: dict, model: str,
                 started: float, stream: bool):
    usage: dict = {}
    headers = {"x-mi-upstream": up.name}
    ms = lambda: round((time.perf_counter() - started) * 1000)  # noqa: E731

    if not stream:
        content = await resp.aread()
        await resp.aclose()
        await http.aclose()
        if resp.status_code < 400:
            usage = _usage(json.loads(content).get("usage", {}))
        record(vk, meta, model, up.name, resp.status_code, usage, ms())
        return Response(content, resp.status_code, headers=headers, media_type=resp.headers.get("content-type"))

    async def chunks():
        buffer = b""
        try:
            async for chunk in resp.aiter_bytes():
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    if line.startswith(b"data:") and line[5:].strip() not in (b"", b"[DONE]"):
                        with contextlib.suppress(ValueError):
                            _absorb(usage, json.loads(line[5:]))
                yield chunk
        finally:
            await resp.aclose()
            await http.aclose()
            record(vk, meta, model, up.name, resp.status_code, _usage(usage), ms())

    return StreamingResponse(chunks(), resp.status_code, headers=headers, media_type="text/event-stream")


# ---------------------------------------------------------------- running it beside the API in development

def for_live_calls():
    """The gateway a live run uses: the one MI_GATEWAY names, else one started beside this process. Replay needs none."""
    if not (os.environ.get("LIVE") == "1") or os.environ.get("MI_GATEWAY"):
        return contextlib.nullcontext()
    return embedded()


@contextlib.contextmanager
def embedded(port: int = PORT):
    """Run the gateway in a thread and point this process at it. Production runs it as its own deployable."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    os.environ["MI_GATEWAY"] = f"http://127.0.0.1:{port}"
    try:
        yield os.environ["MI_GATEWAY"]
    finally:
        server.should_exit = True
        thread.join(5)
        os.environ.pop("MI_GATEWAY", None)
