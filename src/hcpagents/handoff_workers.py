"""Each handoff event becomes work for a team.

Review events go to the reviewers. Safety events go to the safety team.
Each safety intake has a 24 hour clock. It starts when the signal came in.
"""

from datetime import UTC, datetime, timedelta

from hcpagents import events, store
from hcpagents.case_core import restore
from hcpagents.infra import QUEUES

DAY_ZERO = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def _when(text: str | None) -> datetime:
    """Read a time. If it is missing or odd, use now."""
    if not text:
        return _now()
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return _now()
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def review_needed(detail: dict) -> None:
    """Put the case in the reviewer queue and tell the reviewers."""
    store.put("mi-reviewer-queue", {"id": f"review-{detail['case']}", "case": detail["case"],
                                    "country": detail["country"], "why": detail["why"], "status": "waiting",
                                    "queued_at": _now().isoformat(timespec="seconds")})
    events.publish("ReviewerNotice", {"case": detail["case"], "country": detail["country"]},
                   key=f"notice-{detail['event_id']}")


def review_overdue(detail: dict) -> None:
    """Mark the case as escalated to the medical lead."""
    doc = store.get("mi-cases", detail["case"])
    if doc is None or doc.get("escalated_to"):
        return
    case = restore(doc)
    moment = _now().isoformat(timespec="seconds")
    doc["escalated_to"] = "medical_lead"
    doc["history"].append({"at": moment, "event": "Escalated to the medical lead",
                           "detail": f"No decision after {detail['waited_s']} seconds"})
    case.audit({"type": "review_escalated", "to": "medical_lead", "waited_s": detail["waited_s"]})
    store.put("mi-cases", doc)


def safety_signal(detail: dict) -> None:
    """Open a safety intake with a 24 hour report clock."""
    received = _when(detail.get("received"))
    store.put("mi-pv-intake", {"id": f"pv-{detail['case']}", "case": detail["case"], "status": "open",
                               "received": received.isoformat(timespec="seconds"),
                               "report_due": (received + DAY_ZERO).isoformat(timespec="seconds"),
                               "signal": {key: value for key, value in detail.items()
                                          if key not in ("tenant", "event_id")}})


HANDLERS = {"ReviewNeeded": review_needed, "ReviewOverdue": review_overdue, "SafetySignal": safety_signal}


def run_once() -> dict[str, int]:
    """Empty each queue that has a handler. Gives back how many events each one handled."""
    handled = {}
    for queue, detail_type in QUEUES.items():
        handler = HANDLERS.get(detail_type)
        if handler:
            handled[queue] = events.consume(queue, handler)
    return handled
