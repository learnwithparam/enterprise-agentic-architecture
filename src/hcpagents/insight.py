"""The insight agent: what several doctors keep raising across channels, for internal teams only (ADR 0024).

A theme is a topic that at least MIN_HCPS different doctors raised. Every theme lists the interactions it
came from, so a reader can check it, and a digest never contains a word of an interaction. Nothing here is
ever sent to a doctor.
"""

import re
from datetime import datetime

from hcpagents import db

MIN_HCPS = 2
SAMPLE = 10
TOPIC_WORDS = {
    "dosing": r"\bdos(e|es|ing|age)\b",
    "renal_impairment": r"\b(renal|kidney)\b",
    "missed_dose": r"\b(missed|forgot|skipped)\b",
    "storage": r"\b(storage|store|fridge|refrigerat\w*)\b",
    "pregnancy": r"\b(pregnan\w*|breast-?feed\w*)\b",
}


def digest(since: datetime | None = None) -> list[dict]:
    """Themes raised by at least MIN_HCPS doctors, biggest first: {topic, hcps, channels, interactions, sources},
    optionally only from interactions received since a moment."""
    with db.session() as conn:
        rows = conn.execute("SELECT id, channel, body, hcp_id FROM interactions WHERE hcp_id IS NOT NULL "
                            "AND (%s::timestamptz IS NULL OR received_at >= %s) ORDER BY occurred_at DESC",
                            (since, since)).fetchall()
    out = []
    for topic, pattern in TOPIC_WORDS.items():
        hits = [r for r in rows if re.search(pattern, r["body"], re.IGNORECASE)]
        hcps = {r["hcp_id"] for r in hits}
        if len(hcps) >= MIN_HCPS:
            out.append({"topic": topic, "hcps": len(hcps), "channels": sorted({r["channel"] for r in hits}),
                        "interactions": len(hits), "sources": [r["id"] for r in hits[:SAMPLE]]})
    return sorted(out, key=lambda t: (-t["hcps"], t["topic"]))
