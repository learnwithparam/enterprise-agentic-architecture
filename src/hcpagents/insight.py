"""The insight agent shows what many doctors keep raising. It is for internal teams only (ADR 0024).

A theme is a topic that at least MIN_HCPS different doctors raised. Each theme lists the interactions it came from,
so a reader can check it. A digest never holds a word of an interaction. Nothing here is ever sent to a doctor.
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


def _biggest_first(theme: dict) -> tuple:
    return -theme["hcps"], theme["topic"]


def digest(since: datetime | None = None) -> list[dict]:
    """Themes that at least MIN_HCPS doctors raised, biggest first. Pass a time to see only newer interactions."""
    with db.session() as conn:
        rows = conn.execute("SELECT id, channel, body, hcp_id FROM interactions WHERE hcp_id IS NOT NULL "
                            "AND (%s::timestamptz IS NULL OR received_at >= %s) ORDER BY occurred_at DESC",
                            (since, since)).fetchall()
    themes = []
    for topic, pattern in TOPIC_WORDS.items():
        hits = [row for row in rows if re.search(pattern, row["body"], re.IGNORECASE)]
        hcps = {row["hcp_id"] for row in hits}
        if len(hcps) >= MIN_HCPS:
            themes.append({"topic": topic, "hcps": len(hcps), "channels": sorted({row["channel"] for row in hits}),
                           "interactions": len(hits), "sources": [row["id"] for row in hits[:SAMPLE]]})
    return sorted(themes, key=_biggest_first)
