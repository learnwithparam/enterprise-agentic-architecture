"""Shared memory is a set of notes about one doctor. One agent writes a note and others read it.

Each note needs a tenant, a source and an end date. A note without them is refused, and it is checked again on read.
"""

from datetime import date, timedelta

from hcpagents import store, world

TABLE = "mi-memory"
LIFETIME_DAYS = 30
REQUIRED = ("id", "hcp", "text", "source", "expires_on", "author")


class Refused(ValueError):
    """The note failed a check, so it was not written."""


def _problem(note: dict, today: date) -> str | None:
    for field in REQUIRED:
        if not note.get(field):
            return f"The note has no {field}"
    if note.get("tenant", world.current_tenant()) != world.current_tenant():
        return "The note belongs to another tenant"
    if date.fromisoformat(note["expires_on"]) < today:
        return "The note has already expired"
    return None


def remember(note: dict, today: date = world.TODAY) -> dict:
    """Write a note after the checks. The tenant is set here, never taken on trust."""
    problem = _problem(note, today)
    if problem:
        raise Refused(problem)
    saved = note | {"tenant": world.current_tenant()}
    store.put(TABLE, saved)
    return saved


def expiry(today: date = world.TODAY) -> str:
    """The default expiry for a new note."""
    return (today + timedelta(days=LIFETIME_DAYS)).isoformat()


def recall(hcp_id: str, today: date = world.TODAY) -> list[dict]:
    """The notes about one doctor that still pass every check."""
    notes = [note for note in store.scan(TABLE) if note.get("hcp") == hcp_id]
    return [note for note in notes if note.get("tenant") == world.current_tenant() and not note.get("erased") and _problem(note, today) is None]


def forget(hcp_id: str) -> int:
    """Erase a doctor's notes. The text goes, the note is marked erased, and a read never returns it."""
    count = 0
    for note in store.scan(TABLE):
        if note.get("hcp") == hcp_id and note.get("tenant") == world.current_tenant():
            store.put(TABLE, note | {"text": "", "erased": True})
            count += 1
    return count
