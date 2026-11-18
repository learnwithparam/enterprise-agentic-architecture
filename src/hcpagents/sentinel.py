"""The sentinel reads each new note from any channel (ADR 0024).

A rep's CRM note that mentions a rash may be a safety event, even if nobody asked a question.
The sentinel checks each new interaction with the fixed safety screen. The inquiry graph uses the same floor.
On a hit, it hands the signal to pharmacovigilance and freezes contact with that doctor.
It acts alone only to lower risk. It can freeze, but it can never lift a freeze.
"""

from datetime import UTC, datetime

from hcpagents import db, events, ledger, parallel, rules, store

QUEUE = "mi-interactions"


def _interaction(interaction_id: str) -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT id, channel, kind, body, hcp_id FROM interactions WHERE id = %s",
                            (interaction_id,)).fetchone()


def _perceive(event: dict) -> bool:
    # Step 1: Read the note and run the safety screen.
    row = _interaction(event["interaction"])
    hits = []
    if row:
        hits = rules.safety_screen(row["body"])
    # Step 2: A note with no hit is left alone.
    if not hits:
        return False
    case = f"pv-{row['id']}"
    # Step 3: Hand the signal to pharmacovigilance.
    events.publish("SafetySignal", {"case": case, "channel": row["channel"], "interaction": row["id"],
                                    "hcp": row["hcp_id"], "signals": hits}, key=case)
    # Step 4: Freeze contact with that doctor.
    if row["hcp_id"]:
        store.put("mi-freezes", {"id": f"freeze-{row['id']}", "hcp": row["hcp_id"], "case": case,
                                 "interaction": row["id"], "at": datetime.now(UTC).isoformat(timespec="seconds")})
    # Step 5: Write the signal to the ledger.
    ledger.append({"type": "sentinel_signal", "agent": "safety-sentinel", "case": case, "channel": row["channel"],
                   "interaction": row["id"], "frozen": bool(row["hcp_id"]), "kinds": sorted({hit["kind"] for hit in hits})})
    return True


def perceive() -> int:
    """Screen each interaction waiting on the queue. Gives back how many it read."""
    return events.consume(QUEUE, _perceive)


def _sweep(hcp_id: str) -> int:
    """Screen every note of one doctor that has no freeze yet. Gives back how many signals it raised."""
    with db.session() as conn:
        rows = conn.execute("SELECT id FROM interactions WHERE hcp_id = %s ORDER BY id", (hcp_id,)).fetchall()
    raised = 0
    for row in rows:
        if store.get("mi-freezes", f"freeze-{row['id']}") is None:
            raised += _perceive({"interaction": row["id"]})
    return raised


def _job(hcp_id: str):
    def work() -> int:
        return _sweep(hcp_id)

    return work


def scan_doctors(hcp_ids: list[str], timeout_s: float = parallel.TIMEOUT_S) -> dict:
    """Catch up on many doctors at once, one worker each. A failed or late worker is recorded and never blocks the rest."""
    return parallel.fan_out({hcp_id: _job(hcp_id) for hcp_id in hcp_ids}, timeout_s)
