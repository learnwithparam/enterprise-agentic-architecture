"""The rule screen is a floor. A safety model that fails or is capped never takes a rule hit away."""

import asyncio

import pytest

from hcpagents import agent_caps, agents, graph, rules
from tests.live_g_support import install

ADVERSE = {"id": "inq-ae-1", "channel": "portal", "hcp": "hcp-kaya",
           "text": "My patient developed a severe rash after Veltrona. Where should it be stored?"}


def test_the_rule_screen_finds_the_adverse_event_in_the_test_message():
    assert rules.safety_screen(ADVERSE["text"])


def test_a_capped_safety_model_still_routes_a_rule_hit_to_pharmacovigilance(monkeypatch):
    case, rig = install(monkeypatch, ADVERSE)
    case.doc["agent_calls"] = [{"agent": "assembler", "attempts": 1} for _ in range(agent_caps.MAX_HOPS)]
    out = asyncio.run(case.safety_screen({}))
    assert out["facts"] == {"ae": True}
    assert case.doc["signals"] and case.doc["signals"][0]["source"] == "rule"
    assert graph.decide({"ae": True})["route"] == "pv"


def test_a_failing_safety_model_still_keeps_the_rule_hit(monkeypatch):
    case, rig = install(monkeypatch, ADVERSE)

    async def broken(*args, **kwargs):
        raise agents.EscalateToHuman("the model is down")

    monkeypatch.setattr(agents, "call", broken)
    out = asyncio.run(case.safety_screen({}))
    assert out["facts"]["ae"] is True


def test_a_failing_safety_model_with_no_rule_hit_still_goes_to_a_person(monkeypatch):
    case, rig = install(monkeypatch)

    async def broken(*args, **kwargs):
        raise agents.EscalateToHuman("the model is down")

    monkeypatch.setattr(agents, "call", broken)
    with pytest.raises(agents.EscalateToHuman):
        asyncio.run(case.safety_screen({}))
