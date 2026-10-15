"""Ground replies with approved blocks: every sentence a doctor reads is traced to a current approved block."""

import copy

from hcpagents import grounding, world

STORE = {b["id"]: b for b in world.blocks()}


def draft(ids=("VEL-DE-DOSE",)):
    return grounding.compose("VEL", "DE", list(ids), STORE)


def test_a_reply_composed_from_current_blocks_traces_every_sentence():
    v = grounding.verify(draft(), "VEL", "DE", STORE)
    assert v["grounded"], v["problems"]
    assert all(s["ok"] and s["version"] and s["mlr_ref"] for s in v["sentences"])


def test_a_paraphrase_is_not_evidence():
    segs = draft()
    segs[1]["text"] = segs[1]["text"].replace(".", ", as most patients find.", 1)
    assert not grounding.verify(segs, "VEL", "DE", STORE)["grounded"]


def test_a_block_withdrawn_after_drafting_leaves_its_sentences_untraced():
    later = copy.deepcopy(STORE)
    later["VEL-DE-DOSE"]["status"] = "withdrawn"
    v = grounding.verify(draft(), "VEL", "DE", later)
    dose = [s for s in v["sentences"] if s["block_id"] == "VEL-DE-DOSE"]
    assert dose and not any(s["ok"] for s in dose)


def test_the_us_label_is_not_evidence_for_a_german_reply():
    assert not grounding.verify(grounding.compose("VEL", "DE", ["VEL-US-INTER"], STORE), "VEL", "DE", STORE)["grounded"]
