"""Live labs 16 and 18. A refused pick is told what was wrong. A failed check gets one redraft, then a person."""

import asyncio
import json

from hcpagents import agent_redraft, grounding, graph, plan, world
from tests.live_g_support import install

CONTENT = {block["id"]: block for block in world.blocks()}
STORAGE = "Where should Veltrona be stored?"
QUESTIONS = [{"text": STORAGE, "topic": "storage"}]


def pick(*ids: str) -> dict:
    return {"answers": [{"question": STORAGE, "block_ids": list(ids)}], "uncovered": []}


def run_redraft(first_ids, redrafts):
    """Drive the one redraft function. `redrafts` is what each redraft call returns."""
    asked = []

    def check(ids):
        segments = grounding.compose("VEL", "DE", ids, CONTENT)
        return segments, grounding.verify(segments, "VEL", "DE", CONTENT)

    async def redraft(problems):
        asked.append(problems)
        return redrafts[len(asked) - 1]
    return asyncio.run(agent_redraft.verify_with_one_redraft(first_ids, check, redraft)), asked


def test_a_grounded_reply_is_never_redrafted():
    result, asked = run_redraft(["VEL-DE-STOR3"], [])
    assert result["verification"]["grounded"] and result["redrafts"] == 0 and asked == []


def test_a_withdrawn_block_gets_one_redraft_that_can_fix_it():
    result, asked = run_redraft(["VEL-DE-STOR"], [["VEL-DE-STOR3"]])
    assert len(asked) == 1 and asked[0] and result["redrafts"] == 1 and result["verification"]["grounded"]


def test_a_redraft_that_still_fails_is_not_tried_again_and_stays_ungrounded():
    result, asked = run_redraft(["VEL-DE-STOR"], [["VEL-DE-STOR"], ["VEL-DE-STOR3"]])
    assert len(asked) == 1 and result["redrafts"] == 1 and not result["verification"]["grounded"]


def test_a_redraft_with_no_usable_block_is_not_grounded():
    result, asked = run_redraft(["VEL-DE-STOR"], [[]])
    assert len(asked) == 1 and not result["verification"]["grounded"]
    assert "The redraft chose no usable block" in result["verification"]["problems"]


def test_a_redraft_may_use_only_current_blocks_a_tool_returned_for_this_case():
    seen = {"VEL-DE-STOR", "VEL-DE-STOR3", "VEL-US-STOR"}
    args = (seen, CONTENT, "VEL", "DE", 1)
    assert agent_redraft.usable_ids(pick("VEL-DE-STOR3"), *args) == ["VEL-DE-STOR3"]
    assert agent_redraft.usable_ids(pick("VEL-DE-STOR"), *args) == []  # withdrawn
    assert agent_redraft.usable_ids(pick("VEL-US-STOR"), *args) == []  # other country
    assert agent_redraft.usable_ids(pick("VEL-DE-STOR3"), {"VEL-DE-DOSE"}, CONTENT, "VEL", "DE", 1) == []  # no tool returned it
    assert agent_redraft.usable_ids({"answers": [], "uncovered": []}, *args) == []  # a question left unanswered


def test_a_case_redrafts_once_through_the_assembler_and_audits_why(monkeypatch):
    case, rig = install(monkeypatch)
    case.doc["questions"] = QUESTIONS
    case.doc["selection"] = {"answers": pick("VEL-DE-STOR")["answers"]}
    rig.replies.append({"output": pick("VEL-DE-STOR3"), "tool_calls": [{"returned": ["VEL-DE-STOR3"]}]})
    out = asyncio.run(case.verify({}))
    assert out["facts"] == {"grounded": True} and case.doc["redrafts"] == 1 and len(rig.prompts) == 1
    assert json.loads(rig.prompts[0])["redraft"]["problems"] and "redraft" in rig.ledger_types()


def test_a_case_whose_redraft_fails_goes_to_the_reviewer_route(monkeypatch):
    case, rig = install(monkeypatch)
    case.doc["questions"] = QUESTIONS
    case.doc["selection"] = {"answers": pick("VEL-DE-STOR")["answers"]}
    rig.replies.append({"output": pick("VEL-DE-STOR"), "tool_calls": [{"returned": ["VEL-DE-STOR"]}]})
    out = asyncio.run(case.verify({}))
    assert out["facts"] == {"grounded": False} and len(rig.prompts) == 1
    facts = {"ae": False, "verified_hcp": True, "injection": False, "intent": "medical_question", "known_product": True,
             "in_scope": True, "covered": True, "grounded": False}
    assert graph.decide(facts)["route"] == "review"


def test_a_refused_id_is_named_in_the_next_prompt_and_a_clean_first_pick_adds_nothing():
    clean = json.loads(plan._prompt("VEL", "DE", QUESTIONS, [STORAGE], []))
    assert "refused_ids" not in clean["retry"]
    fed = json.loads(plan._prompt("VEL", "DE", QUESTIONS, [STORAGE], ["VEL-US-STOR"]))
    assert fed["retry"]["refused_ids"] == ["VEL-US-STOR"] and "Choose only ids a search returns" in fed["retry"]["refused_note"]
    assert "retry" not in json.loads(plan._prompt("VEL", "DE", QUESTIONS, [], ["VEL-US-STOR"]))


def test_the_plan_feeds_a_refused_id_back_and_stops_at_the_attempt_limit():
    prompts, replies = [], iter([(pick("VEL-US-STOR"), ["VEL-US-STOR"])] * 3)

    async def ask(prompt):
        prompts.append(json.loads(prompt))
        out, seen = next(replies)
        return out, set(seen)
    result = asyncio.run(plan.run(ask, "VEL", "DE", QUESTIONS, CONTENT))
    assert len(prompts) == plan.MAX_ATTEMPTS and prompts[1]["retry"]["refused_ids"] == ["VEL-US-STOR"] and result["uncovered"]
