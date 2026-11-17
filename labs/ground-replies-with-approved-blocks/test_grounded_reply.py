"""Ground replies with approved blocks. Each sentence a doctor reads comes from a current approved block."""

import copy

from hcpagents import grounding, world

STORE = {block["id"]: block for block in world.blocks()}


def draft(ids=("VEL-DE-DOSE",)):
    return grounding.compose("VEL", "DE", list(ids), STORE)


def test_a_reply_composed_from_current_blocks_traces_every_sentence():
    verdict = grounding.verify(draft(), "VEL", "DE", STORE)
    assert verdict["grounded"], verdict["problems"]
    assert all(sentence["ok"] and sentence["version"] and sentence["mlr_ref"] for sentence in verdict["sentences"])


def test_a_paraphrase_is_not_evidence():
    segs = draft()
    segs[1]["text"] = segs[1]["text"].replace(".", ", as most patients find.", 1)
    assert not grounding.verify(segs, "VEL", "DE", STORE)["grounded"]


def test_a_block_withdrawn_after_drafting_leaves_its_sentences_untraced():
    later = copy.deepcopy(STORE)
    later["VEL-DE-DOSE"]["status"] = "withdrawn"
    verdict = grounding.verify(draft(), "VEL", "DE", later)
    dose = [sentence for sentence in verdict["sentences"] if sentence["block_id"] == "VEL-DE-DOSE"]
    assert dose and not any(sentence["ok"] for sentence in dose)


def test_the_us_label_is_not_evidence_for_a_german_reply():
    reply = grounding.compose("VEL", "DE", ["VEL-US-INTER"], STORE)
    assert not grounding.verify(reply, "VEL", "DE", STORE)["grounded"]
