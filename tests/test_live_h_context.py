"""A question gets its own context, and a delegated step sees only that context."""

import json

from hcpagents import context, delegation, world

BLOCKS = {block["id"]: block for block in world.blocks()}
KAYA = world.hcp("hcp-kaya")


def ids(brief: dict) -> list[str]:
    return [block["id"] for block in brief["blocks"]]


def test_the_context_for_a_question_holds_only_that_doctors_country_and_product():
    brief = context.for_question(KAYA, "VEL", "storage", "How do I store it?", BLOCKS)
    assert ids(brief) == ["VEL-DE-STOR3"]
    assert brief["facets"]["country"]["code"] == "DE"
    assert brief["facets"]["scope"]["country"] == "DE"


def test_without_a_topic_every_current_block_of_that_product_and_country_comes_and_no_other():
    brief = context.for_question(KAYA, "VEL", None, "Tell me about it", BLOCKS)
    for block_id in ids(brief):
        assert BLOCKS[block_id]["product"] == "VEL" and BLOCKS[block_id]["country"] == "DE"
    assert "VEL-US-DOSE" not in ids(brief) and "OMB-DE-DOSE" not in ids(brief) and "VEL-DE-STOR" not in ids(brief)


def test_a_delegated_step_gets_only_the_narrow_brief_never_the_case_or_the_doctor():
    seen = []

    def spy(brief: dict) -> dict:
        seen.append(brief)
        return delegation.specialist(brief)

    out = delegation.delegate("inq-1", KAYA, "VEL", "dosing", "What dose?", BLOCKS, step=spy, record=lambda entry: None)
    assert out["accepted"] and out["block_ids"] == ["VEL-DE-DOSE"]
    assert tuple(seen[0]) == context.FIELDS
    text = json.dumps(seen[0])
    for private in (KAYA["name"], KAYA["email"], KAYA["registry_id"], KAYA["records"]["crm"], "hcp-kaya", "inq-1"):
        assert private not in text


def test_an_answer_naming_a_block_outside_the_brief_is_refused_and_written_to_the_ledger():
    rows = []

    def greedy(_brief: dict) -> dict:
        return {"block_ids": ["VEL-DE-DOSE", "VEL-US-DOSE"]}

    out = delegation.delegate("inq-2", KAYA, "VEL", "dosing", "What dose?", BLOCKS, step=greedy, record=rows.append)
    assert not out["accepted"] and out["block_ids"] == []
    assert rows[0]["type"] == "delegation" and rows[0]["accepted"] is False and "VEL-US-DOSE was not in the brief" in rows[0]["problems"]


def test_an_answer_with_no_block_is_refused():
    out = delegation.delegate("inq-3", KAYA, "VEL", "dosing", "x", BLOCKS, step=lambda _brief: {"block_ids": []}, record=lambda entry: None)
    assert not out["accepted"]
