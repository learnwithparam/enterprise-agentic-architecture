"""Keep safety intake moving. A failed detector hands notes to a person and drops none."""

from datetime import UTC, datetime, timedelta

import pytest

from hcpagents import events, ledger, safety_clock, sentinel, store


@pytest.fixture
def docs(monkeypatch):
    rows: dict[tuple[str, str], dict] = {}

    def get(table, doc_id):
        return rows.get((table, doc_id))

    def put(table, doc):
        rows[(table, doc["id"])] = doc

    def scan(table):
        return [doc for (name, _), doc in rows.items() if name == table]

    def nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(store, "get", get)
    monkeypatch.setattr(store, "put", put)
    monkeypatch.setattr(store, "scan", scan)
    monkeypatch.setattr(ledger, "append", nothing)
    monkeypatch.setattr(events, "publish", nothing)
    return rows


def test_a_note_read_while_the_detector_is_down_goes_to_a_person(docs, monkeypatch):
    stale = datetime.now(UTC) - timedelta(hours=3)
    store.put(safety_clock.HEALTH, {"id": "detector", "last_healthy": stale.isoformat()})
    def rash_note(interaction_id):
        return {"id": interaction_id, "channel": "crm", "kind": "note", "body": "patient developed a rash", "hcp_id": None}

    monkeypatch.setattr(sentinel, "_interaction", rash_note)
    assert sentinel._perceive({"interaction": "i-1"}) is False
    assert (safety_clock.MANUAL_QUEUE, "manual-i-1") in docs


def test_a_friday_signal_is_due_for_acknowledgment_on_monday():
    friday = datetime(2026, 11, 20, 16, 0, tzinfo=UTC)
    assert safety_clock.ack_due(friday).date().isoformat() == "2026-11-23"


def test_an_overdue_intake_is_flagged_once_and_an_acknowledged_one_never(docs):
    store.put(safety_clock.INTAKES, {"id": "pv-a", "case": "a", "ack_due": "2026-11-23T16:00:00+00:00"})
    store.put(safety_clock.INTAKES, {"id": "pv-b", "case": "b", "ack_due": "2026-11-23T16:00:00+00:00"})
    safety_clock.acknowledge("b", "pv-intake-1")
    later = datetime(2026, 12, 1, tzinfo=UTC)
    assert safety_clock.overdue_acks(later) == ["a"]
    assert safety_clock.overdue_acks(later) == []
