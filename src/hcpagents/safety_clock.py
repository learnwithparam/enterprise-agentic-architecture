"""The safety team's two clocks, and what happens when the detector stops.

An intake must be acknowledged within one business day. The report clock is the 24 hours in handoff_workers.
If the detector has not reported healthy for two hours, every event goes to a person to screen. Nothing is dropped.
"""

from datetime import UTC, datetime, timedelta

from hcpagents import ledger, store

HEALTH = "mi-detector-health"
MANUAL_QUEUE = "mi-pv-manual-screening"
INTAKES = "mi-pv-intake"
OUTAGE_LIMIT = timedelta(hours=2)
WEEKEND = (5, 6)


def _now() -> datetime:
    return datetime.now(UTC)


def add_business_days(start: datetime, days: int) -> datetime:
    """Count weekdays only. Public holidays are a known limit of this build."""
    moment = start
    while days > 0:
        moment += timedelta(days=1)
        if moment.weekday() not in WEEKEND:
            days -= 1
    return moment


def ack_due(received: datetime) -> datetime:
    """One business day after the signal came in."""
    return add_business_days(received, 1)


def acknowledge(case_id: str, who: str) -> dict:
    """The safety team confirms it has the signal. The ledger records who and when."""
    intake = store.get(INTAKES, f"pv-{case_id}")
    if intake is None:
        raise KeyError(f"No safety intake for {case_id}")
    moment = _now().isoformat(timespec="seconds")
    intake = intake | {"acknowledged_by": who, "acknowledged_at": moment}
    store.put(INTAKES, intake)
    ledger.append({"type": "pv_acknowledged", "case": case_id, "by": who})
    return intake


def overdue_acks(now: datetime | None = None) -> list[str]:
    """Intakes past their acknowledgment time. Each one is on the ledger once."""
    moment = now or _now()
    late = []
    for intake in store.scan(INTAKES):
        if intake.get("acknowledged_at") or intake.get("ack_overdue"):
            continue
        if datetime.fromisoformat(intake["ack_due"]) < moment:
            store.put(INTAKES, intake | {"ack_overdue": True})
            ledger.append({"type": "pv_ack_overdue", "case": intake["case"], "due": intake["ack_due"]})
            late.append(intake["case"])
    return late


def heartbeat() -> None:
    """The detector calls this after each healthy pass."""
    store.put(HEALTH, {"id": "detector", "last_healthy": _now().isoformat(timespec="seconds")})


def detector_is_down(now: datetime | None = None) -> bool:
    """Down means no healthy pass for two hours. A detector that never reported is not down yet."""
    row = store.get(HEALTH, "detector")
    if row is None:
        return False
    return (now or _now()) - datetime.fromisoformat(row["last_healthy"]) > OUTAGE_LIMIT


def send_to_manual_screening(event: dict, reason: str) -> None:
    """A person screens this event. It stays in the queue until they do."""
    store.put(MANUAL_QUEUE, {"id": f"manual-{event['id']}", "event": event, "reason": reason,
                             "queued_at": _now().isoformat(timespec="seconds"), "status": "waiting"})
    ledger.append({"type": "detector_down", "event": event["id"], "reason": reason})
