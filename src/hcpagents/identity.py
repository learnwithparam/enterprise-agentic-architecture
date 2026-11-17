"""Which doctor does a channel id belong to? This module finds out (ADR 0022).

Each channel knows a doctor by a different handle. It may be a CRM id, a marketing id, a phone number or a portal email.
The tenant's doctor list maps each handle to one person. The national registry id works on any channel.

A handle that matches nobody, or more than one person, stays unresolved. A guess could put one doctor's words
in another doctor's 360. So a human links it.
"""

import re

from hcpagents import db, world


def _norm(channel: str, value: str) -> str:
    """Phones match by digits and emails by lower case. So formatting never splits one doctor in two."""
    if channel == "contact_centre":
        return re.sub(r"\D", "", value)
    return value.strip().lower()


def resolve(channel: str, source_id: str) -> str | None:
    """The doctor id in this tenant that owns the handle, or None if it is not known or not clear."""
    wanted = _norm(channel, source_id)
    found = {doctor["id"] for doctor in world.hcp_world()["hcp"]
             if wanted in (_norm(channel, doctor["records"].get(channel, "")), _norm("registry", doctor["registry_id"]))}
    if len(found) == 1:
        return found.pop()
    return None


def link_pending() -> int:
    """Match each interaction that has no person yet. This is for handles that became known later."""
    linked = 0
    with db.session() as conn:
        rows = conn.execute("SELECT id, channel, source_id FROM interactions WHERE hcp_id IS NULL").fetchall()
        for row in rows:
            hcp_id = resolve(row["channel"], row["source_id"])
            if hcp_id:
                conn.execute("UPDATE interactions SET hcp_id = %s WHERE id = %s", (hcp_id, row["id"]))
                linked += 1
    return linked


def unresolved() -> list[dict]:
    """What a human still has to link, newest first."""
    with db.session() as conn:
        return conn.execute("SELECT id, channel, source_id, kind, occurred_at FROM interactions "
                            "WHERE hcp_id IS NULL ORDER BY occurred_at DESC").fetchall()


def interactions(hcp_id: str) -> list[dict]:
    """The notes each channel holds about one doctor, newest first."""
    with db.session() as conn:
        return conn.execute("SELECT id, channel, kind, body, occurred_at FROM interactions "
                            "WHERE hcp_id = %s ORDER BY occurred_at DESC", (hcp_id,)).fetchall()
