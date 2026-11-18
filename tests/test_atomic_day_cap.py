"""The day cap holds when many workers ask at once, and a run that ends in review still pays for its calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from hcpagents import agent_caps, agents, store
from tests.live_g_support import install


@pytest.mark.floci
def test_twenty_workers_adding_at_once_lose_nothing():
    doc_id = f"atomic-{id(object())}"
    with ThreadPoolExecutor(20) as pool:
        list(pool.map(lambda _: store.add_to("mi-usage", doc_id, "calls", 1), range(20)))
    assert store.get("mi-usage", doc_id)["calls"] == 20


@pytest.mark.floci
def test_ten_workers_racing_for_five_calls_leave_exactly_five_through():
    cap = agent_caps.calls_today() + 5
    with ThreadPoolExecutor(10) as pool:
        answers = list(pool.map(lambda _: agent_caps.reserve(cap), range(10)))
    assert answers.count(None) == 5
    assert agent_caps.calls_today() == cap
    store.add_to("mi-usage", agent_caps.day_id(), "calls", -5)


def test_a_run_that_fails_twice_and_goes_to_review_is_charged_for_both_calls(monkeypatch):
    case, rig = install(monkeypatch)

    async def gives_up(*_args):
        error = agents.EscalateToHuman("assembler: no model left")
        error.attempts = 2
        raise error

    monkeypatch.setattr(agents, "call", gives_up)
    with pytest.raises(agents.EscalateToHuman):
        asyncio.run(case.agent("assembler", "x"))
    assert agent_caps.calls_today() == 2
    assert agent_caps.calls_made(case.doc["agent_calls"]) == 2


def test_a_run_that_made_no_call_gives_its_reserved_call_back(monkeypatch):
    case, rig = install(monkeypatch)

    async def has_no_budget(*_args):
        raise agents.EscalateToHuman("assembler: no budget")

    monkeypatch.setattr(agents, "call", has_no_budget)
    with pytest.raises(agents.EscalateToHuman):
        asyncio.run(case.agent("assembler", "x"))
    assert agent_caps.calls_today() == 0 and case.doc["agent_calls"] == []


def test_check_alone_refuses_a_tenant_at_the_day_cap():
    assert "day cap" in agent_caps.check([], day_cap=0)
    assert agent_caps.check([], day_cap=agent_caps.calls_today() + 1) is None
