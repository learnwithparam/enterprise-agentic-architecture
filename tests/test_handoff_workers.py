"""Each handoff event reaches the team that owns it."""

from datetime import datetime, timedelta

import pytest

from hcpagents import events, handoff_workers, ledger, store
from tests.test_flow import fresh, run  # noqa: F401 - fresh is an autouse fixture

pytestmark = pytest.mark.floci


def test_a_review_needed_event_lands_in_the_reviewer_queue():
    events.publish("ReviewNeeded", {"case": "inq-x", "country": "DE", "why": "Off label"})
    assert handoff_workers.run_once()["mi-medical-review"] == 1
    item = store.get("mi-reviewer-queue", "review-inq-x")
    assert item["status"] == "waiting" and item["why"] == "Off label"


def test_a_review_overdue_event_escalates_the_case_once():
    run("inq-103")
    handoff_workers.review_overdue({"case": "inq-103", "country": "DE", "waited_s": 900})
    handoff_workers.review_overdue({"case": "inq-103", "country": "DE", "waited_s": 1800})
    doc = store.get("mi-cases", "inq-103")
    assert doc["escalated_to"] == "medical_lead"
    assert [step["event"] for step in doc["history"]].count("Escalated to the medical lead") == 1
    types = [row["entry"]["type"] for row in ledger.entries("inq-103")]
    assert types.count("review_escalated") == 1


def test_a_safety_signal_opens_an_intake_with_a_24_hour_clock():
    events.publish("SafetySignal", {"case": "inq-y", "country": "DE", "received": "2026-10-01T08:00:00+00:00"})
    assert handoff_workers.run_once()["mi-pv-intake"] == 1
    intake = store.get("mi-pv-intake", "pv-inq-y")
    due = datetime.fromisoformat(intake["report_due"]) - datetime.fromisoformat(intake["received"])
    assert intake["status"] == "open" and due == timedelta(hours=24)
