"""A handoff reaches the receiver once, is on the ledger, and shared memory shows in the 360 (needs Floci)."""

from datetime import date

import pytest

from hcpagents import handoff_workers, ledger, memory, store
from tests.test_flow import fresh  # noqa: F401 - an autouse fixture

pytestmark = pytest.mark.floci

NOTE = {"id": "n-1", "hcp": "hcp-kaya", "text": "Prefers email", "source": "crm:CRM-DE-00412", "expires_on": "2026-12-01",
        "author": "outreach-coordinator"}


def test_a_handoff_is_written_to_the_ledger_and_read_once_by_the_receiver():
    record = handoff_workers.hand_off("inquiry-agent", "pharmacovigilance", "inq-9", "Rash reported")
    assert handoff_workers.hand_off("inquiry-agent", "pharmacovigilance", "inq-9", "Rash reported") == record
    assert (record["from"], record["to"], record["case"], record["reason"]) == ("inquiry-agent", "pharmacovigilance", "inq-9", "Rash reported")
    assert [item["case"] for item in handoff_workers.receive("pharmacovigilance")] == ["inq-9"]
    assert handoff_workers.receive("pharmacovigilance") == []
    types = [row["entry"]["type"] for row in ledger.entries("inq-9")]
    assert types == ["handoff", "handoff_received"]


def test_a_safety_signal_event_leaves_a_handoff_for_pharmacovigilance():
    handoff_workers.safety_signal({"case": "inq-y", "country": "DE", "received": "2026-10-01T08:00:00+00:00"})
    assert store.get("mi-handoffs", "handoff-pharmacovigilance-inq-y")["status"] == "open"


def test_a_note_written_for_a_doctor_shows_in_their_360_until_it_expires():
    memory.remember(NOTE | {"expires_on": "2026-12-01"})
    assert [note["id"] for note in memory.recall("hcp-kaya")] == ["n-1"]
    assert memory.recall("hcp-kaya", date(2026, 12, 2)) == []


def test_erasing_a_doctor_wipes_their_shared_memory_notes():
    from hcpagents import case_review, world

    memory.remember(NOTE, today=date(2026, 11, 1))
    assert memory.recall("hcp-kaya", today=date(2026, 11, 2))
    case_review.erase_person("hcp-kaya", world.person("u-raman"))
    assert memory.recall("hcp-kaya", today=date(2026, 11, 2)) == []
    assert store.get(memory.TABLE, "n-1")["text"] == ""
