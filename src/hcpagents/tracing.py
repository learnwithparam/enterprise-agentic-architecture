"""One trace for each case, with personal data hidden (ADR 0027).

The case record already holds each step as a span. This module replays them as OpenTelemetry spans
to a backend that the environment picks. It sends to Langfuse Cloud when both Langfuse keys are set,
and to Arize Phoenix when MI_PHOENIX_URL is set. Else it sends nowhere. The spans are the same either way.
"""

import base64
import json
import os
import re
from functools import cache

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from hcpagents import world

MAX_TEXT = 400
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")


def redact(text: str, names: tuple[str, ...] = ()) -> str:
    """Take out what names a person: emails, phone numbers and the names given. Then cut it short."""
    for name in names:
        text = re.sub(re.escape(name), "[name]", text, flags=re.IGNORECASE)
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))[:MAX_TEXT]


def _endpoint() -> tuple[str, dict] | None:
    public_key, secret_key = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if public_key and secret_key:
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        return f"{host}/api/public/otel/v1/traces", {"Authorization": f"Basic {auth}"}
    url = os.environ.get("MI_PHOENIX_URL")
    if url:
        return f"{url.rstrip('/')}/v1/traces", {}
    return None


@cache
def provider() -> TracerProvider | None:
    target = _endpoint()
    if target is None:
        return None
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=target[0], headers=target[1])))
    return tracer_provider


def _names(case: dict) -> tuple[str, ...]:
    name = (case.get("hcp") or {}).get("name", "")
    return tuple(part for part in (name, *name.split()) if len(part) > 2)


def _attrs(span: dict, names: tuple[str, ...]) -> dict:
    attributes = {"mi.step": span["name"],
                  "mi.input": redact(json.dumps(span["input"], default=str, ensure_ascii=False), names),
                  "mi.output": redact(json.dumps(span["output"], default=str, ensure_ascii=False), names)}
    if span.get("model"):
        usage = span.get("usage") or {}
        attributes |= {"gen_ai.system": "anthropic", "gen_ai.operation.name": "chat",
                       "gen_ai.request.model": span["model"],
                       "gen_ai.usage.input_tokens": int(usage.get("input_tokens", 0)),
                       "gen_ai.usage.output_tokens": int(usage.get("output_tokens", 0))}
    return attributes


def export_case(case: dict, tracer_provider: TracerProvider | None = None) -> None:
    """Send the case as one trace: a root span for the case and a child for each step."""
    tracer_provider = tracer_provider or provider()
    if tracer_provider is None:
        return
    tracer, names = tracer_provider.get_tracer("hcpagents"), _names(case)
    with tracer.start_as_current_span("case", attributes={
            "mi.case": case["id"], "mi.tenant": world.current_tenant(), "mi.release": case.get("release", "unknown"),
            "mi.route": case["route"], "mi.rule": case["decision"]["rule"], "mi.country": case["country"] or "unknown",
            "mi.cost_usd": case["cost_usd"], "mi.latency_ms": case["latency_ms"], "mi.trace_id": case["trace"]["id"]}):
        for span in case["trace"]["spans"]:
            with tracer.start_as_current_span(span["name"], attributes=_attrs(span, names)):
                pass
