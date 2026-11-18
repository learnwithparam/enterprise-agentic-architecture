"""Delegate with a narrow brief. The helper sees only the question's context, and the lead checks what comes back."""

import copy
import json

from hcpagents import context, delegation, world

BLOCKS = {block["id"]: block for block in world.blocks()}
DOCTOR = world.hcp("hcp-kaya")


def ignore(_entry: dict) -> None:
    """The ledger needs Floci, so this lab drops the entry."""


def ask(step, content=BLOCKS):
    return delegation.delegate("inq-1", DOCTOR, "VEL", "storage", "How do I store it?", content, step=step, record=ignore)


def wrong_country(_brief):
    return {"block_ids": ["VEL-US-STOR"]}


def test_step_1_the_brief_holds_one_country_and_one_product_and_no_doctor():
    # Step 1
    brief = context.for_question(DOCTOR, "VEL", "storage", "How do I store it?", BLOCKS)
    assert [block["id"] for block in brief["blocks"]] == ["VEL-DE-STOR3"]
    assert DOCTOR["name"] not in json.dumps(brief)


def test_step_2_the_specialist_receives_a_copy_of_the_brief_and_nothing_else():
    # Step 2
    seen = []

    def spy(brief):
        seen.append(brief)
        return delegation.specialist(brief)

    assert ask(spy)["accepted"]
    assert tuple(seen[0]) == context.FIELDS
    for private in (DOCTOR["email"], DOCTOR["registry_id"], "inq-1"):
        assert private not in json.dumps(seen[0])


def test_step_3_the_lead_refuses_a_block_that_is_not_in_the_brief():
    # Step 3
    out = ask(wrong_country)
    assert not out["accepted"] and out["problems"] == ["VEL-US-STOR was not in the brief"]


def test_step_4_the_lead_refuses_a_block_that_is_no_longer_current():
    # Step 4
    later = copy.deepcopy(BLOCKS)

    def withdraw_then_answer(brief):
        later["VEL-DE-STOR3"]["status"] = "withdrawn"
        return delegation.specialist(brief)

    out = ask(withdraw_then_answer, later)
    assert not out["accepted"] and "withdrawn" in out["problems"][0]
