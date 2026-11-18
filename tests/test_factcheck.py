"""Free email copy is checked sentence by sentence against approved content."""

import copy

import pytest

from hcpagents import factcheck, store, world

BLOCKS = {block["id"]: block for block in world.blocks()}
DOSE = BLOCKS["VEL-DE-DOSE"]["text"]
US_ONLY = BLOCKS["VEL-US-PED"]["text"]


@pytest.fixture
def content(monkeypatch):
    monkeypatch.setattr(store, "content", lambda: copy.deepcopy(BLOCKS))


def statuses(text: str, country: str = "DE") -> list[str]:
    return [row["status"] for row in factcheck.check_copy(text, "VEL", country)["sentences"]]


def test_an_approved_sentence_passes(content):
    out = factcheck.check_copy(DOSE, "VEL", "DE")
    assert out["ok"] is True
    assert [row["block_id"] for row in out["sentences"]] == ["VEL-DE-DOSE"] * 2


def test_an_invented_sentence_is_flagged(content):
    out = factcheck.check_copy(f"{DOSE} Veltrona clears skin in two weeks.", "VEL", "DE")
    assert out["ok"] is False
    assert statuses(f"{DOSE} Veltrona clears skin in two weeks.")[-1] == "unapproved"
    assert out["sentences"][-1]["block_id"] is None


def test_a_block_approved_only_in_another_country_is_flagged_wrong_country(content):
    assert statuses(US_ONLY, "US") == ["approved"]
    assert statuses(US_ONLY, "DE") == ["wrong_country"]


def test_a_withdrawn_block_is_flagged(monkeypatch):
    later = copy.deepcopy(BLOCKS)
    later["VEL-DE-DOSE"]["status"] = "withdrawn"
    monkeypatch.setattr(store, "content", lambda: later)
    assert set(statuses(DOSE)) == {"withdrawn"}
