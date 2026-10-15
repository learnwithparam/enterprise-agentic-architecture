"""Prove the audit trail with a hash chain: an edit to any past entry is found, and the archive outlives it."""

import copy

import pytest

from hcpagents import ledger

ENTRIES = [{"type": "case_received", "case": "inq-105"},
           {"type": "routed", "case": "inq-105", "route": "pv"},
           {"type": "handoff", "case": "inq-105", "to": "pharmacovigilance"}]


def chain(entries):
    prev, rows = ledger.GENESIS, []
    for e in copy.deepcopy(entries):
        h = ledger.digest(prev, e)
        rows.append({"prev": prev, "entry": e, "hash": h})
        prev = h
    return rows


def first_break(rows):
    prev = ledger.GENESIS
    for i, r in enumerate(rows):
        if r["prev"] != prev or ledger.digest(prev, r["entry"]) != r["hash"]:
            return i
        prev = r["hash"]
    return None


def test_an_untouched_chain_verifies():
    assert first_break(chain(ENTRIES)) is None


def test_each_hash_covers_the_one_before_it():
    assert ledger.digest("a" * 64, ENTRIES[0]) != ledger.digest("b" * 64, ENTRIES[0])


def test_editing_a_past_route_breaks_the_chain_at_that_entry():
    rows = chain(ENTRIES)
    rows[1]["entry"]["route"] = "send"
    assert first_break(rows) == 1


def test_rewriting_that_hash_too_only_moves_the_break_to_the_next_entry():
    rows = chain(ENTRIES)
    rows[1]["entry"]["route"] = "send"
    rows[1]["hash"] = ledger.digest(rows[1]["prev"], rows[1]["entry"])
    assert first_break(rows) == 2


@pytest.mark.floci
def test_the_archived_copy_cannot_be_deleted():
    seq = ledger.append({"type": "lab", "note": "archive check"})["seq"]
    assert ledger.try_delete_archive(seq)["deleted"] is False
    assert ledger.verify()["ok"]
