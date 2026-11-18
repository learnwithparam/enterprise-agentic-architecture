"""Redraft a failed check once. Then a person reviews. A refused id is named in the next try."""

import asyncio
import json

from hcpagents import agent_redraft, grounding, plan, world

CONTENT = {block["id"]: block for block in world.blocks()}
STORAGE = "Where should Veltrona be stored?"
QUESTIONS = [{"text": STORAGE, "topic": "storage"}]


def check(ids):
    segments = grounding.compose("VEL", "DE", ids, CONTENT)
    return segments, grounding.verify(segments, "VEL", "DE", CONTENT)


def run_redraft(first_ids, answers):
    asked = []

    async def redraft(problems):
        asked.append(problems)
        return answers[len(asked) - 1]

    return asyncio.run(agent_redraft.verify_with_one_redraft(first_ids, check, redraft)), asked


def test_a_grounded_reply_is_never_redrafted():
    result, asked = run_redraft(["VEL-DE-STOR3"], [])
    assert result["verification"]["grounded"] and asked == []


def test_a_withdrawn_block_gets_one_redraft_that_can_fix_it():
    result, asked = run_redraft(["VEL-DE-STOR"], [["VEL-DE-STOR3"]])
    assert len(asked) == 1 and result["verification"]["grounded"]


def test_a_redraft_that_still_fails_is_not_tried_again():
    result, asked = run_redraft(["VEL-DE-STOR"], [["VEL-DE-STOR"], ["VEL-DE-STOR3"]])
    assert len(asked) == 1 and not result["verification"]["grounded"]


def test_a_redraft_with_no_usable_block_is_not_grounded():
    result, asked = run_redraft(["VEL-DE-STOR"], [[]])
    assert len(asked) == 1 and not result["verification"]["grounded"]


def test_a_refused_id_is_named_in_the_next_prompt():
    prompt = json.loads(plan._prompt("VEL", "DE", QUESTIONS, [STORAGE], ["VEL-US-STOR"]))
    assert prompt["retry"]["refused_ids"] == ["VEL-US-STOR"]
    assert "refused_ids" not in json.loads(plan._prompt("VEL", "DE", QUESTIONS, [STORAGE], []))["retry"]
