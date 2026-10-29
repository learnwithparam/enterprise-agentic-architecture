"""The safety sentinel's perception: it reads every interaction that lands on any channel (ADR 0024).

A rep's CRM note that mentions a rash is a possible adverse event even though nobody asked a question.
The sentinel screens each new interaction with the deterministic safety screen, the same floor the
inquiry graph uses. On a hit it hands the signal to pharmacovigilance and freezes contact with that
doctor. It acts alone only in the risk-reducing direction: it can freeze, it can never lift a freeze.
"""

from datetime import UTC, datetime

from hcpagents import db, events, ledger, rules, store

QUEUE = "mi-interactions"


def _interaction(interaction_id: str) -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT id, channel, kind, body, hcp_id FROM interactions WHERE id = %s", (interaction_id,)).fetchone()


def _perceive(event: dict) -> None:
    row = _interaction(event["interaction"])
    hits = rules.safety_screen(row["body"]) if row else []
    if not hits:
        return
    case = f"pv-{row['id']}"
    events.publish("SafetySignal", {"case": case, "channel": row["channel"], "interaction": row["id"],
                                    "hcp": row["hcp_id"], "signals": hits}, key=case)
    if row["hcp_id"]:
        store.put("mi-freezes", {"id": f"freeze-{row['id']}", "hcp": row["hcp_id"], "case": case,
                                 "interaction": row["id"], "at": datetime.now(UTC).isoformat(timespec="seconds")})
    ledger.append({"type": "sentinel_signal", "agent": "safety-sentinel", "case": case, "channel": row["channel"],
                   "interaction": row["id"], "frozen": bool(row["hcp_id"]), "kinds": sorted({h["kind"] for h in hits})})


def perceive() -> int:
    """Screen every interaction waiting on the queue. Returns how many were read."""
    return events.consume(QUEUE, _perceive)
