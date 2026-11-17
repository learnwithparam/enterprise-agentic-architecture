"""Outreach picks the next contact for each doctor. No two contacts overlap (ADR 0023).

It reads HCP 360. For each planned touch it decides if a human may be asked to approve it.
It acts alone only to hold a touch, never to send one. A propose result means a rep or marketer still has to approve.

Each reason names the rule that fired and the case or touch behind it. Each hold is written to the ledger.
So Compliance can see why a doctor was not contacted.
"""

from hcpagents import hcp360, ledger, store, supervisor


def _held_reasons(view: dict) -> dict:
    held = {}
    for planned in view["planned"]:
        decision = planned["decision"]
        if decision["go"]:
            continue
        held[planned["id"]] = [_reason(rule, why, view["open_cases"], view["freezes"])
                               for rule, why in zip(decision["rules"], decision["reasons"], strict=True)]
    return held


def coordinate(hcp_id: str) -> list[dict]:
    """One decision for each planned touch, oldest first. Each has an id, an action (propose or hold) and a list of reasons."""
    view = hcp360.view(hcp_id)
    held = _held_reasons(view)
    clear = [planned for planned in view["planned"] if planned["decision"]["go"]]
    for loser, winner in supervisor.arbitrate(clear).items():
        held[loser] = [{"rule": "overlap", "why": f"Yields to {winner}, planned within {supervisor.OVERLAP_DAYS} days",
                        "source": winner}]
    decisions = []
    for planned in view["planned"]:
        action = "propose"
        if planned["id"] in held:
            action = "hold"
        decisions.append({"id": planned["id"], "on": planned["on"], "action": action,
                          "reasons": held.get(planned["id"], [])})
    return decisions


def _reason(rule: str, why: str, cases: list[dict], freezes: list[dict]) -> dict:
    source = None
    if rule == "open_medical_case" and cases:
        source = cases[0]["id"]
    elif rule == "safety_freeze" and freezes:
        source = freezes[0]["interaction"]
    return {"rule": rule, "why": why, "source": source}


def run(hcp_id: str) -> list[dict]:
    """Coordinate, store the decision on the touch, and ledger each hold."""
    decisions = coordinate(hcp_id)
    for decision in decisions:
        touch = store.get("mi-touches", decision["id"])
        if touch.get("coordinator") != decision["action"]:
            store.put("mi-touches", touch | {"coordinator": decision["action"], "reasons": decision["reasons"]})
            if decision["action"] == "hold":
                ledger.append({"type": "outreach_hold", "agent": "outreach-coordinator", "touch": decision["id"],
                               "hcp": hcp_id, "rules": [reason["rule"] for reason in decision["reasons"]]})
    return decisions
