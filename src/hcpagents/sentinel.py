"""The sentinel reads each new note from any channel (ADR 0024).

A rep's CRM note that mentions a rash may be a safety event, even if nobody asked a question.
The sentinel checks each new interaction with the fixed safety screen. The inquiry graph uses the same floor.
On a hit, it hands the signal to pharmacovigilance and freezes contact with that doctor.
It acts alone only to lower risk. It can freeze, but it can never lift a freeze.
"""

from datetime import UTC, datetime

from hcpagents import db, events, ledger, rules, store

QUEUE = "mi-interactions"


def _interaction(interaction_id: str) -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT id, channel, kind, body, hcp_id FROM interactions WHERE id = %s",
                            (interaction_id,)).fetchone()


def _perceive(event: dict) -> None:
    row = _interaction(event["interaction"])
    hits = []
    if row:
        hits = rules.safety_screen(row["body"])
    if not hits:
        return
    case = f"pv-{row['id']}"
    events.publish("SafetySignal", {"case": case, "channel": row["channel"], "interaction": row["id"],
                                    "hcp": row["hcp_id"], "signals": hits}, key=case)
    if row["hcp_id"]:
        store.put("mi-freezes", {"id": f"freeze-{row['id']}", "hcp": row["hcp_id"], "case": case,
                                 "interaction": row["id"], "at": datetime.now(UTC).isoformat(timespec="seconds")})
    ledger.append({"type": "sentinel_signal", "agent": "safety-sentinel", "case": case, "channel": row["channel"],
                   "interaction": row["id"], "frozen": bool(row["hcp_id"]), "kinds": sorted({hit["kind"] for hit in hits})})


def perceive() -> int:
    """Screen each interaction waiting on the queue. Gives back how many it read."""
    return events.consume(QUEUE, _perceive)
