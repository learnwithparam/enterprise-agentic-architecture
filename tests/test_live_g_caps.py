"""Live lab 22. A case and a tenant cannot make more model calls than a cap. The refusal is explicit and audited."""

import asyncio
import ast
from pathlib import Path

import pytest

from hcpagents import agent_caps, agents, kernel
from tests.live_g_support import install

SRC = Path(__file__).resolve().parents[1] / "src" / "hcpagents"


def ran(count: int, attempts: int = 1) -> list[dict]:
    return [{"agent": "assembler", "attempts": attempts} for _ in range(count)]


def refused(monkeypatch, agent_calls=None, usage=None):
    case, rig = install(monkeypatch)
    case.doc["agent_calls"] = agent_calls or []
    if usage is not None:
        rig.documents[f"{agent_caps.USAGE_TABLE}/{agent_caps.day_id()}"] = {"id": agent_caps.day_id(), "calls": usage}
    rig.replies.append({"output": {"signals": []}})
    with pytest.raises(agent_caps.CapExceeded) as caught:
        asyncio.run(case.agent("safety", "x"))
    return case, rig, caught.value


def test_a_case_at_the_hop_cap_makes_no_further_call(monkeypatch):
    case, rig, error = refused(monkeypatch, ran(agent_caps.MAX_HOPS))
    assert rig.prompts == [] and "hop cap" in str(error)
    assert [e for e in rig.entries if e["type"] == "cap_refused"][0]["why"].startswith(f"{agent_caps.MAX_HOPS} agent runs")


def test_a_case_at_the_call_cap_makes_no_further_call_even_below_the_hop_cap(monkeypatch):
    _, rig, error = refused(monkeypatch, ran(2, attempts=agent_caps.MAX_CALLS_PER_CASE // 2))
    assert rig.prompts == [] and "case cap" in str(error)


def test_a_tenant_at_the_day_cap_makes_no_further_call(monkeypatch):
    _, rig, error = refused(monkeypatch, usage=agent_caps.TENANT_CALLS_PER_DAY)
    assert rig.prompts == [] and "day cap" in str(error)
    assert "cap_refused" in rig.ledger_types()


def test_a_call_under_every_cap_runs_and_is_charged_by_its_attempts(monkeypatch):
    case, rig = install(monkeypatch)
    rig.replies.append({"output": {"signals": []}})
    asyncio.run(case.agent("safety", "x"))
    assert len(rig.prompts) == 1 and agent_caps.calls_today() == 1
    assert "cap_refused" not in rig.ledger_types()


def test_a_cap_refusal_sends_the_case_to_review_with_its_own_rule(monkeypatch):
    _, _, error = refused(monkeypatch, ran(agent_caps.MAX_HOPS))
    assert isinstance(error, agents.EscalateToHuman)
    decision = kernel.escalation(error)["decision"]
    assert decision["route"] == "review" and decision["rule"] == "cap_exceeded"


def test_the_caps_leave_room_for_the_longest_honest_case():
    assert agent_caps.MAX_HOPS >= 5 and agent_caps.MAX_CALLS_PER_CASE >= 10


def test_a_model_call_is_made_in_one_place_and_the_caps_are_checked_first():
    callers = [path.name for path in SRC.glob("*.py") if "agents.call(" in path.read_text()]
    assert callers == ["case_core.py"]
    tree = ast.parse((SRC / "case_core.py").read_text())
    agent = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "agent")
    first_line = {}
    for node in ast.walk(agent):
        if isinstance(node, ast.Attribute):
            first_line[node.attr] = min(node.lineno, first_line.get(node.attr, node.lineno))
    assert first_line["refuse_over_cap"] < first_line["call"]
