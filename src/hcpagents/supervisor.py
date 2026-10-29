"""The supervisor settles conflicts between agents' proposals by policy, never by asking a model (ADR 0023).

Two proposals to the same doctor conflict when they fall within OVERLAP_DAYS of each other. The one that
serves the doctor's own need wins: a non-promotional touch beats a promotional one, then the earlier date
wins. The loser is held, not deleted, and keeps the id of the proposal it yielded to.
"""

from datetime import date

OVERLAP_DAYS = 3


def _rank(p: dict) -> tuple:
    return (bool(p.get("promotional")), p["on"], p["id"])


def _conflict(a: dict, b: dict) -> bool:
    return abs((date.fromisoformat(a["on"][:10]) - date.fromisoformat(b["on"][:10])).days) <= OVERLAP_DAYS


def arbitrate(proposals: list[dict]) -> dict[str, str]:
    """Map each losing proposal id to the id of the proposal it yields to. Winners are absent."""
    yields: dict[str, str] = {}
    for p in sorted(proposals, key=_rank):
        winner = next((w for w in sorted(proposals, key=_rank)
                       if w["id"] != p["id"] and w["id"] not in yields and _conflict(w, p) and _rank(w) < _rank(p)), None)
        if winner:
            yields[p["id"]] = winner["id"]
    return yields
