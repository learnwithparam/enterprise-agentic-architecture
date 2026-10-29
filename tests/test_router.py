"""The router picks Haiku or Sonnet, escalates once, then hands the call to a human, and never leaves the allowlist."""

import asyncio

import pytest

from hcpagents import agents, cases, router
from hcpagents.router import HAIKU, SONNET, Outcome, route

FAILED_HAIKU = (Outcome(HAIKU, router.SCHEMA_FAILURE),)


def test_every_task_class_lands_on_an_allowed_model():
    for task in router.HAIKU_TASKS | router.SONNET_TASKS:
        assert route(task).model in agents.ALLOWED_MODELS


def test_high_volume_work_starts_on_haiku_and_open_ended_work_on_sonnet():
    assert {route(t).model for t in router.HAIKU_TASKS} == {HAIKU}
    assert {route(t).model for t in router.SONNET_TASKS} == {SONNET}


def test_a_schema_failure_escalates_to_sonnet_and_a_second_failure_goes_to_a_human():
    assert route("classify", prior=FAILED_HAIKU).model == SONNET
    both = FAILED_HAIKU + (Outcome(SONNET, router.SCHEMA_FAILURE),)
    assert route("classify", prior=both).model is None


def test_low_confidence_escalates_only_when_the_risk_is_high():
    doubt = (Outcome(HAIKU, router.LOW_CONFIDENCE),)
    assert route("screen", "high", prior=doubt).model == SONNET
    assert route("screen", "low", prior=doubt).model == HAIKU


def test_no_budget_for_sonnet_means_a_human_not_a_cheaper_guess():
    assert route("plan", budget_left_usd=0.0).model is None
    assert route("classify", prior=FAILED_HAIKU, budget_left_usd=0.0).model is None
    assert route("classify", budget_left_usd=0.0).model == HAIKU


def test_unknown_inputs_are_refused():
    with pytest.raises(ValueError):
        route("write_reply")
    with pytest.raises(ValueError):
        route("classify", "medium")


def test_the_call_retries_once_on_sonnet_then_escalates(monkeypatch):
    tried = []

    async def always_fails(model, *_a):
        tried.append(model)
        raise agents.AgentFailed("no structured output")

    monkeypatch.setattr(agents, "_call_on", lambda model, *a: always_fails(model, *a))
    with pytest.raises(agents.EscalateToHuman):
        asyncio.run(agents.call("triage", "x", {"id": "route-test"}, {}, None, None))
    assert tried == [HAIKU, SONNET]


def test_sonnet_is_priced_as_sonnet_when_it_answers(monkeypatch):
    async def ok(model, *_a):
        return {"model": model, "cost_usd": agents.cost_usd({"input_tokens": 1_000_000}, model)}

    monkeypatch.setattr(agents, "_call_on", ok)
    rec = asyncio.run(agents.call("triage", "x", {"id": "price-test"}, {}, None, None))
    assert rec["model"] == HAIKU and rec["cost_usd"] == 0.10


def test_an_escalated_case_goes_to_review_with_nothing_drafted(monkeypatch):
    async def escalate(*_a, **_k):
        raise agents.EscalateToHuman("triage: Sonnet already failed this call; a human takes it")

    monkeypatch.setattr(agents, "call", escalate)
    d = asyncio.run(cases.run("inq-101"))
    assert d["route"] == "review" and d["decision"]["rule"] == "router_escalated"
    assert d["draft"] is None and d["status"] != "sent"
