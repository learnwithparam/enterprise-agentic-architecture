"""The safety team's acknowledgment clock and the two-hour detector outage fallback. Fakes the store and ledger in memory."""

from datetime import UTC, datetime, timedelta

import pytest

from hcpagents import events, ledger, safety_clock, sentinel, store


@pytest.fixture
def rig(monkeypatch):
    docs: dict[tuple[str, str], dict] = {}
    entries: list[dict] = []
    monkeypatch.setattr(store, "get", lambda table, doc_id: docs.get((table, doc_id)))
    monkeypatch.setattr(store, "put", lambda table, doc: docs.__setitem__((table, doc["id"]), doc))
    monkeypatch.setattr(store, "scan", lambda table: [doc for (name, _), doc in docs.items() if name == table])
    monkeypatch.setattr(ledger, "append", lambda entry, subject=None, private=None: entries.append(entry))
    monkeypatch.setattr(events, "publish", lambda *args, **kwargs: None)
    monkeypatch.setattr(sentinel.store, "put", lambda table, doc: docs.__setitem__((table, doc["id"]), doc))
    return docs, entries


FRIDAY = datetime(2026, 11, 20, 16, 0, tzinfo=UTC)


def test_the_acknowledgment_is_due_one_business_day_later():
    assert safety_clock.ack_due(FRIDAY).date().isoformat() == "2026-11-23"  # Monday
    assert safety_clock.ack_due(FRIDAY - timedelta(days=1)).date().isoformat() == "2026-11-20"


def test_an_intake_past_its_acknowledgment_time_is_flagged_once(rig):
    docs, entries = rig
    store.put("mi-pv-intake", {"id": "pv-a", "case": "a", "ack_due": "2026-11-23T16:00:00+00:00"})
    assert safety_clock.overdue_acks(FRIDAY) == []
    late = FRIDAY + timedelta(days=4)
    assert safety_clock.overdue_acks(late) == ["a"]
    assert safety_clock.overdue_acks(late) == []
    assert [e["type"] for e in entries].count("pv_ack_overdue") == 1


def test_an_acknowledged_intake_is_never_flagged(rig):
    store.put("mi-pv-intake", {"id": "pv-b", "case": "b", "ack_due": "2026-11-23T16:00:00+00:00"})
    safety_clock.acknowledge("b", "pv-intake-1")
    assert safety_clock.overdue_acks(FRIDAY + timedelta(days=9)) == []


def test_a_detector_silent_for_over_two_hours_is_down(rig):
    safety_clock.heartbeat()
    assert not safety_clock.detector_is_down()
    assert safety_clock.detector_is_down(datetime.now(UTC) + timedelta(hours=2, minutes=1))


def test_a_down_detector_sends_every_note_to_manual_screening_and_drops_none(rig, monkeypatch):
    docs, entries = rig
    store.put(safety_clock.HEALTH, {"id": "detector", "last_healthy": (datetime.now(UTC) - timedelta(hours=3)).isoformat()})
    monkeypatch.setattr(sentinel, "_interaction", lambda _id: {"id": _id, "channel": "crm", "kind": "note",
                                                               "body": "patient had a severe rash", "hcp_id": "hcp-kaya"})
    for number in range(3):
        assert sentinel._perceive({"interaction": f"i-{number}"}) is False
    queued = [key for key in docs if key[0] == safety_clock.MANUAL_QUEUE]
    assert len(queued) == 3
    assert [e["type"] for e in entries].count("detector_down") == 3


def test_a_detector_that_raises_sends_the_note_to_manual_screening(rig, monkeypatch):
    docs, _ = rig

    def broken(_id):
        raise ConnectionError("database away")

    monkeypatch.setattr(sentinel, "_interaction", broken)
    assert sentinel._perceive({"interaction": "i-9"}) is False
    assert (safety_clock.MANUAL_QUEUE, "manual-i-9") in docs


def test_a_healthy_pass_keeps_the_detector_up(rig, monkeypatch):
    docs, _ = rig
    monkeypatch.setattr(sentinel, "_interaction", lambda _id: {"id": _id, "channel": "crm", "kind": "note",
                                                               "body": "routine visit", "hcp_id": None})
    assert sentinel._perceive({"interaction": "i-1"}) is False
    assert (safety_clock.HEALTH, "detector") in docs
