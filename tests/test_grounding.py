"""The verifier is what makes "zero hallucination" a property instead of a hope."""

import copy

from hcpagents import grounding, world

STORE = {b["id"]: b for b in world.blocks()}


def reply(ids=("VEL-DE-DOSE", "VEL-DE-ADMIN")):
    return grounding.compose("VEL", "DE", list(ids), STORE)


def test_a_reply_built_from_current_blocks_is_grounded():
    v = grounding.verify(reply(), "VEL", "DE", STORE)
    assert v["grounded"], v["problems"]
    assert all(s["ok"] and s["block_id"] for s in v["sentences"])


def test_reply_order_is_opening_answers_safety_disclosure_closing():
    ids = [s["block_id"] for s in reply()]
    assert ids == ["TPL-OPEN", "VEL-DE-DOSE", "VEL-DE-ADMIN", "ISI-VEL-DE", "TPL-AI-DE", "TPL-CLOSE"]


def test_one_changed_word_fails_the_check():
    segs = reply()
    segs[1]["text"] = segs[1]["text"].replace("15 mg", "30 mg")
    v = grounding.verify(segs, "VEL", "DE", STORE)
    assert not v["grounded"]
    assert any("not found" in p for p in v["problems"])


def test_an_invented_sentence_fails_the_check():
    segs = reply()
    segs.insert(2, {"block_id": "VEL-DE-DOSE", "version": 3, "text": "Veltrona clears skin in two weeks.", "role": "answer"})
    assert not grounding.verify(segs, "VEL", "DE", STORE)["grounded"]


def test_a_block_withdrawn_after_drafting_fails_at_send_time():
    segs = reply()
    later = copy.deepcopy(STORE)
    later["VEL-DE-ADMIN"]["status"] = "withdrawn"
    v = grounding.verify(segs, "VEL", "DE", later)
    assert not v["grounded"]
    assert any("withdrawn" in p for p in v["problems"])
    admin = [s for s in v["sentences"] if s["block_id"] == "VEL-DE-ADMIN"]
    assert admin and not any(s["ok"] for s in admin)


def test_another_countrys_block_is_not_evidence():
    segs = grounding.compose("VEL", "DE", ["VEL-US-INTER"], STORE)
    assert not grounding.verify(segs, "VEL", "DE", STORE)["grounded"]


def test_an_expired_block_is_not_evidence():
    segs = grounding.compose("OMB", "JP", ["OMB-JP-INTER"], STORE)
    v = grounding.verify(segs, "OMB", "JP", STORE)
    assert any("expired" in p for p in v["problems"])


def test_the_safety_information_cannot_be_left_out():
    segs = [s for s in reply() if not s["block_id"].startswith("ISI-")]
    assert "Required block ISI-VEL-DE is missing" in grounding.verify(segs, "VEL", "DE", STORE)["problems"]


def test_another_products_block_is_not_evidence():
    segs = grounding.compose("VEL", "DE", ["OMB-DE-DOSE"], STORE)
    assert not grounding.verify(segs, "VEL", "DE", STORE)["grounded"]
