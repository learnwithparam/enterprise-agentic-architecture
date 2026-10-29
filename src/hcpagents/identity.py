"""Identity resolution: which doctor does a channel's own id belong to (ADR 0022).

Each channel knows a doctor by a different handle: a CRM id, a marketing id, a phone number, a portal email.
The tenant's HCP list maps every handle to one person, and the national registry id works on any channel.
A handle that matches nobody, or more than one person, stays unresolved. Guessing would put a doctor's
words in another doctor's 360, so a human links it instead.
"""

import re

from hcpagents import db, world


def _norm(channel: str, value: str) -> str:
    """Phones compare by digits and emails by lower case, so formatting never splits one doctor in two."""
    if channel == "contact_centre":
        return re.sub(r"\D", "", value)
    return value.strip().lower()


def resolve(channel: str, source_id: str) -> str | None:
    """The HCP id in the current tenant that owns this handle, or None when it is unknown or ambiguous."""
    wanted = _norm(channel, source_id)
    found = {h["id"] for h in world.hcp_world()["hcp"]
             if wanted in (_norm(channel, h["records"].get(channel, "")), _norm("registry", h["registry_id"]))}
    return found.pop() if len(found) == 1 else None


def link_pending() -> int:
    """Resolve every interaction still without a person, for handles that became known after they arrived."""
    linked = 0
    with db.session() as conn:
        rows = conn.execute("SELECT id, channel, source_id FROM interactions WHERE hcp_id IS NULL").fetchall()
        for r in rows:
            hcp_id = resolve(r["channel"], r["source_id"])
            if hcp_id:
                conn.execute("UPDATE interactions SET hcp_id = %s WHERE id = %s", (hcp_id, r["id"]))
                linked += 1
    return linked


def unresolved() -> list[dict]:
    """What a human still has to link, newest first."""
    with db.session() as conn:
        return conn.execute("SELECT id, channel, source_id, kind, occurred_at FROM interactions "
                            "WHERE hcp_id IS NULL ORDER BY occurred_at DESC").fetchall()


def interactions(hcp_id: str) -> list[dict]:
    """Everything the channels said about one doctor, newest first."""
    with db.session() as conn:
        return conn.execute("SELECT id, channel, kind, body, occurred_at FROM interactions "
                            "WHERE hcp_id = %s ORDER BY occurred_at DESC", (hcp_id,)).fetchall()
