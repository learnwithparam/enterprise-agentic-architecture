"""The AI gateway. Every model call goes through it (ADR 0019).

The gateway speaks the Anthropic API. The Agent SDK points ANTHROPIC_BASE_URL at it and needs no other change.
An agent holds a virtual key, never the real key. The key stands for a tenant, an agent and a budget.
For each call the gateway checks the key, the model and the budget. Then it sends the call to the first upstream that answers.
It writes one spend row with the tenant, agent, release, prompt version and case.

Start it with: uv run uvicorn hcpagents.gateway:app --port 8766
"""

import asyncio
import contextlib
import json
import os
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

from hcpagents import aws
from hcpagents.agents import ALLOWED_MODELS
from hcpagents.aws import client
from hcpagents.gateway_keys import Refused, _hash, issue_key, key_for, record, resolve, revoke, spend_by
from hcpagents.gateway_translate import BEDROCK_MODELS, as_events, from_converse, to_converse

__all__ = ["BEDROCK_MODELS", "PORT", "Refused", "Upstream", "_hash", "app", "embedded", "for_live_calls", "from_converse",
           "issue_key", "key_for", "release", "resolve", "revoke", "spend_by", "to_converse", "upstreams"]

PORT = 8766
RETRY_STATUS = {429, 500, 502, 503, 504, 529}  # The provider is busy or down, so try the next upstream.
FORWARD = ("content-type", "anthropic-version", "anthropic-beta")
USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def release() -> str:
    """The release this process runs. It is MI_RELEASE if set, else the hash of its manifest (ADR 0025)."""
    from hcpagents import releases  # Late import, because releases reads this file.
    return os.environ.get("MI_RELEASE") or releases.current()


@dataclass
class Upstream:
    name: str
    base_url: str
    key: str
    transport: httpx.AsyncBaseTransport | None = None
    kind: str = "messages"  # Messages is the normal kind. Bedrock is turned into Converse.
    client: object | None = None  # A bedrock-runtime client, built on first use when None.


def upstreams() -> list[Upstream]:
    """Anthropic is first. Bedrock is next if a region is set. Last is a backup endpoint, if one is set."""
    out = [Upstream("anthropic", "https://api.anthropic.com", os.environ.get("ANTHROPIC_API_KEY", ""))]
    if os.environ.get("MI_BEDROCK_REGION"):
        out.append(Upstream("bedrock", "", "", kind="bedrock"))
    fallback_url = os.environ.get("MI_GATEWAY_FALLBACK_URL")
    if fallback_url:
        out.append(Upstream("fallback", fallback_url, os.environ.get("MI_GATEWAY_FALLBACK_KEY", "")))
    return out


# ---------------------------------------------------------------- Amazon Bedrock

def _bedrock(upstream: Upstream):
    if upstream.client is None:
        if aws.ENDPOINT:
            upstream.client = client("bedrock-runtime")
        else:  # One try only. Moving to the next upstream is the job of the gateway.
            upstream.client = boto3.client("bedrock-runtime", region_name=os.environ["MI_BEDROCK_REGION"],
                                           config=Config(read_timeout=120, retries={"max_attempts": 1}))
    return upstream.client


def _error_response(status: int, kind: str, message: str) -> httpx.Response:
    return httpx.Response(status, json={"type": "error", "error": {"type": kind, "message": message}})


async def _converse(upstream: Upstream, body: dict, model: str) -> httpx.Response:
    """Call Bedrock and answer as the Messages API would.

    Throttling and server errors come back as a status. Then the next upstream is tried.
    """
    def call() -> dict:
        return _bedrock(upstream).converse(**to_converse(body, model))

    try:
        reply = await asyncio.to_thread(call)
    except ClientError as error:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
        return _error_response(status, "api_error", error.response.get("Error", {}).get("Message", "Bedrock refused the call"))
    except BotoCoreError as error:
        raise httpx.TransportError(str(error)) from error
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
    return {name: count for name, count in raw.items() if name in USAGE and isinstance(count, int)}


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _refusal(body: dict, virtual_key: dict) -> JSONResponse | None:
    model = body.get("model")
    if model not in ALLOWED_MODELS:
        return _error(400, "invalid_request_error", f"{model} is not allowed; use one of {sorted(ALLOWED_MODELS)}")
    if virtual_key["spent"] >= virtual_key["budget"]:
        return _error(429, "rate_limit_error",
                      f"The {virtual_key['agent']} key spent ${virtual_key['spent']:.4f} of its ${virtual_key['budget']:.2f} budget")
    return None


async def _forward(upstream: Upstream, body: dict, payload: bytes, headers: dict):
    """Send the call to one upstream. Return the reply and its client. On a failure, close the client and raise."""
    http = httpx.AsyncClient(transport=upstream.transport, base_url=upstream.base_url, timeout=120)
    try:
        if upstream.kind == "bedrock":
            response = await _converse(upstream, body, body["model"])
        else:
            request = http.build_request("POST", "/v1/messages", content=payload, headers=headers | {"x-api-key": upstream.key})
            response = await http.send(request, stream=True)
    except httpx.HTTPError:
        await http.aclose()
        raise
    return response, http


@app.post("/v1/messages")
async def messages(request: Request):
    started = time.perf_counter()
    secret = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        virtual_key = resolve(secret)
    except Refused as error:
        return _error(error.status, error.kind, str(error))
    body = await request.json()
    refusal = _refusal(body, virtual_key)
    if refusal:
        return refusal
    meta = {"case": request.headers.get("x-mi-case", "-"), "release": request.headers.get("x-mi-release", release()),
            "prompt_version": request.headers.get("x-mi-prompt-version", "-")}
    headers = {name: value for name, value in request.headers.items() if name in FORWARD}
    payload = json.dumps(body).encode()

    last: Exception | None = None
    for upstream in upstreams():
        try:
            response, http = await _forward(upstream, body, payload, headers)
        except httpx.HTTPError as error:
            last = error
            continue
        if response.status_code in RETRY_STATUS:
            last = RuntimeError(f"{upstream.name} answered {response.status_code}")
            await response.aclose()
            await http.aclose()
            continue
        return await _relay(response, http, upstream, virtual_key, meta, body["model"], started, bool(body.get("stream")))
    record(virtual_key, meta, body["model"], "none", 502, {}, _elapsed_ms(started))
    return _error(502, "api_error", f"Every upstream failed; last: {last}")


async def _relay_whole(response: httpx.Response, http: httpx.AsyncClient, upstream: Upstream, virtual_key: dict, meta: dict,
                       model: str, started: float):
    usage: dict = {}
    content = await response.aread()
    await response.aclose()
    await http.aclose()
    if response.status_code < 400:
        usage = _usage(json.loads(content).get("usage", {}))
    record(virtual_key, meta, model, upstream.name, response.status_code, usage, _elapsed_ms(started))
    return Response(content, response.status_code, headers={"x-mi-upstream": upstream.name},
                    media_type=response.headers.get("content-type"))


def _relay_stream(response: httpx.Response, http: httpx.AsyncClient, upstream: Upstream, virtual_key: dict, meta: dict,
                  model: str, started: float):
    usage: dict = {}

    async def chunks():
        buffer = b""
        try:
            async for chunk in response.aiter_bytes():
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    if line.startswith(b"data:") and line[5:].strip() not in (b"", b"[DONE]"):
                        with contextlib.suppress(ValueError):
                            _absorb(usage, json.loads(line[5:]))
                yield chunk
        finally:
            await response.aclose()
            await http.aclose()
            record(virtual_key, meta, model, upstream.name, response.status_code, _usage(usage), _elapsed_ms(started))

    return StreamingResponse(chunks(), response.status_code, headers={"x-mi-upstream": upstream.name},
                             media_type="text/event-stream")


async def _relay(response: httpx.Response, http: httpx.AsyncClient, upstream: Upstream, virtual_key: dict, meta: dict,
                 model: str, started: float, stream: bool):
    if not stream:
        return await _relay_whole(response, http, upstream, virtual_key, meta, model, started)
    return _relay_stream(response, http, upstream, virtual_key, meta, model, started)


# ---------------------------------------------------------------- running beside the API

def for_live_calls():
    """The gateway for a live run. Use the one MI_GATEWAY names, or else start one beside this process."""
    if not (os.environ.get("LIVE") == "1") or os.environ.get("MI_GATEWAY"):
        return contextlib.nullcontext()
    return embedded()


@contextlib.contextmanager
def embedded(port: int = PORT):
    """Run the gateway in a thread and point this process at it. In production it is its own service."""
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
