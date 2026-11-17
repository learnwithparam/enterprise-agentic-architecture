"""Rules, not a model, pick the winner when two agent plans clash (ADR 0023).

Two plans for one doctor clash when they fall within OVERLAP_DAYS of each other.
The one that helps the doctor wins. A plain touch beats a promotional one, then the earlier date wins.
The loser is held, not deleted. It keeps the id of the plan it gave way to.
"""

from datetime import date

OVERLAP_DAYS = 3


def _rank(proposal: dict) -> tuple:
    return (bool(proposal.get("promotional")), proposal["on"], proposal["id"])


def _conflict(first: dict, second: dict) -> bool:
    gap = date.fromisoformat(first["on"][:10]) - date.fromisoformat(second["on"][:10])
    return abs(gap.days) <= OVERLAP_DAYS


def arbitrate(proposals: list[dict]) -> dict[str, str]:
    """Map each losing proposal id to the id it yields to. Winners are left out."""
    yields: dict[str, str] = {}
    for proposal in sorted(proposals, key=_rank):
        winner = next((other for other in sorted(proposals, key=_rank)
                       if other["id"] != proposal["id"] and other["id"] not in yields
                       and _conflict(other, proposal) and _rank(other) < _rank(proposal)), None)
        if winner:
            yields[proposal["id"]] = winner["id"]
    return yields
