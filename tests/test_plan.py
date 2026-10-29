"""The assembler's LangGraph plan: it may retry, it may not loop forever, and it may not use an id no tool returned."""

import asyncio
import json

import pytest

from hcpagents import kernel, plan, world

CONTENT = {b["id"]: b for b in world.blocks()}
QUESTIONS = [{"text": "How much do I give?", "topic": "dosing"}, {"text": "Can it go with food?", "topic": "administration"}]


def run(script):
    """Run the plan with an `ask` that returns the next scripted (output, returned ids) pair; returns (result, prompts)."""
    prompts, replies = [], iter(script)

    async def ask(prompt):
        prompts.append(json.loads(prompt))
        out, seen = next(replies)
        return out, set(seen)
    return asyncio.run(plan.run(ask, "VEL", "DE", QUESTIONS, CONTENT)), prompts


def answers(*pairs, uncovered=()):
    return {"answers": [{"question": q, "block_ids": ids} for q, ids in pairs], "uncovered": list(uncovered)}


FULL = answers((QUESTIONS[0]["text"], ["VEL-DE-DOSE"]), (QUESTIONS[1]["text"], ["VEL-DE-ADMIN"]))
SEEN = ["VEL-DE-DOSE", "VEL-DE-ADMIN"]


def test_a_plan_that_covers_every_question_stops_after_one_attempt():
    res, prompts = run([(FULL, SEEN)])
    assert res["attempts"] == 1 and res["uncovered"] == [] and len(prompts) == 1 and "retry" not in prompts[0]


def test_a_gap_makes_the_plan_search_again_naming_what_is_missing():
    first = answers((QUESTIONS[0]["text"], ["VEL-DE-DOSE"]), (QUESTIONS[1]["text"], []), uncovered=[QUESTIONS[1]["text"]])
    res, prompts = run([(first, ["VEL-DE-DOSE"]), (FULL, SEEN)])
    assert res["attempts"] == 2 and res["uncovered"] == []
    assert prompts[1]["retry"]["not_covered"] == [QUESTIONS[1]["text"]]


def test_the_loop_is_bounded_and_what_stays_uncovered_goes_to_a_human():
    gap = answers((QUESTIONS[0]["text"], []), (QUESTIONS[1]["text"], []), uncovered=[QUESTIONS[0]["text"]])
    res, prompts = run([(gap, []), (gap, []), (gap, [])])
    assert res["attempts"] == plan.MAX_ATTEMPTS == len(prompts) and res["uncovered"]


def test_an_id_no_tool_returned_is_rejected_even_if_it_exists():
    res, _ = run([(FULL, ["VEL-DE-DOSE"]), (FULL, ["VEL-DE-DOSE"])])
    assert "VEL-DE-ADMIN" in res["rejected_ids"] and res["uncovered"]


def test_an_id_from_another_country_is_rejected_even_if_a_tool_returned_it():
    other = answers((QUESTIONS[0]["text"], ["VEL-US-DOSE"]), (QUESTIONS[1]["text"], ["VEL-DE-ADMIN"]))
    res, _ = run([(other, ["VEL-US-DOSE", "VEL-DE-ADMIN"]), (other, ["VEL-US-DOSE", "VEL-DE-ADMIN"])])
    assert "VEL-US-DOSE" in res["rejected_ids"]


def test_the_kernel_stops_an_attempt_past_the_limit():
    kernel.check_attempt(plan.MAX_ATTEMPTS, plan.MAX_ATTEMPTS)
    with pytest.raises(kernel.KernelViolation, match="over the limit"):
        kernel.check_attempt(plan.MAX_ATTEMPTS + 1, plan.MAX_ATTEMPTS)


def test_the_compiled_graph_has_exactly_the_declared_edges():
    graph = plan.build(None, "VEL", "DE", QUESTIONS, CONTENT).get_graph()
    assert {(e.source, e.target) for e in graph.edges} == plan.EDGES
