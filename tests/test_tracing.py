"""A case becomes one trace in GenAI conventions, and no personal data leaves with it (ADR 0027)."""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import pytest

from hcpagents import releases, tracing, world

pytestmark = pytest.mark.floci

CASE = {"id": "c-1", "route": "review", "decision": {"rule": "default"}, "country": "DE", "cost_usd": 0.002,
        "latency_ms": 900, "release": "r-abc12345", "hcp": {"name": "Anna Keller"},
        "trace": {"id": "t1", "spans": [
            {"name": "agent.triage", "input": "Dr Anna Keller, anna@clinic.de, +49 30 1234567 asks about dosing",
             "output": {"topic": "dosing"}, "usage": {"input_tokens": 120, "output_tokens": 30}, "model": "claude-haiku-5-5"},
            {"name": "ground", "input": {}, "output": {"ok": True}, "usage": None, "model": None}]}}


def export(case=CASE):
    mem = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(mem))
    with world.as_tenant("quillon"):
        tracing.export_case(case, tp)
    return {s.name: s for s in mem.get_finished_spans()}


def test_redact_removes_emails_phones_and_names():
    out = tracing.redact("Anna Keller wrote anna@clinic.de or +49 30 1234567", ("Anna Keller",))
    assert "Anna" not in out and "@" not in out and "1234567" not in out


def test_no_personal_data_is_exported():
    blob = " ".join(str(dict(s.attributes)) for s in export().values())
    assert "Keller" not in blob and "anna@clinic.de" not in blob and "1234567" not in blob


def test_a_case_is_one_trace_with_a_child_per_step():
    spans = export()
    assert set(spans) == {"case", "agent.triage", "ground"}
    assert len({s.context.trace_id for s in spans.values()}) == 1
    assert spans["agent.triage"].parent.span_id == spans["case"].context.span_id


def test_model_spans_carry_genai_attributes_and_the_release():
    spans = export()
    a = spans["agent.triage"].attributes
    assert a["gen_ai.request.model"] == "claude-haiku-5-5" and a["gen_ai.usage.input_tokens"] == 120
    assert "gen_ai.request.model" not in spans["ground"].attributes
    assert spans["case"].attributes["mi.release"] == "r-abc12345" and spans["case"].attributes["mi.tenant"] == "quillon"


def test_nothing_is_exported_without_a_backend(monkeypatch):
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "MI_PHOENIX_URL"):
        monkeypatch.delenv(k, raising=False)
    tracing.provider.cache_clear()
    assert tracing.provider() is None


def test_langfuse_wins_over_phoenix(monkeypatch):
    monkeypatch.setenv("MI_PHOENIX_URL", "http://localhost:6006")
    assert tracing._endpoint()[0].endswith("/v1/traces") and "6006" in tracing._endpoint()[0]
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    url, headers = tracing._endpoint()
    assert "langfuse" in url and headers["Authorization"].startswith("Basic ")


def test_the_gateway_tags_spend_with_the_manifest_release(monkeypatch):
    from hcpagents import gateway
    monkeypatch.delenv("MI_RELEASE", raising=False)
    assert gateway.release() == releases.current() == releases.release_id()


def test_online_monitors_group_cases_by_release():
    import asyncio

    from fastapi.testclient import TestClient

    from hcpagents import api, cases, infra
    from tests.test_flow import as_user
    infra.provision(reset=True)
    asyncio.run(cases.run("inq-101"))
    rows = TestClient(api.app).get("/api/monitors", headers=as_user("u-brandt")).json()
    mine = next(r for r in rows if r["release"] == releases.current())
    assert mine["cases"] >= 1 and mine["p95_ms"] >= mine["p50_ms"] and mine["avg_cost_usd"] >= 0
    assert TestClient(api.app).get("/api/monitors").status_code == 401
