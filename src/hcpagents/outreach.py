"""Outreach picks the next contact for each doctor. No two contacts overlap (ADR 0023).

It reads HCP 360. For each planned touch it decides if a human may be asked to approve it.
It acts alone only to hold a touch, never to send one. A propose result means a rep or marketer still has to approve.

Each reason names the rule that fired and the case or touch behind it. Each hold is written to the ledger.
So Compliance can see why a doctor was not contacted.
"""

from hcpagents import authz, delivery, hcp360, ledger, store, supervisor, world


class Denied(Exception):
    """This user may not approve for this doctor."""


class Blocked(Exception):
    """The touch may not go now. The message holds the reasons."""


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


def _decision(hcp_id: str, touch_ref) -> dict:
    decisions = coordinate(hcp_id)
    if isinstance(touch_ref, int):
        if not 0 <= touch_ref < len(decisions):
            raise LookupError(f"No planned touch number {touch_ref} for {hcp_id}")
        return decisions[touch_ref]
    found = next((decision for decision in decisions if decision["id"] == touch_ref), None)
    if found is None:
        raise LookupError(f"No planned touch {touch_ref} for {hcp_id}")
    return found


def approve(hcp_id: str, touch_ref: int | str, approver: dict) -> dict:
    """A human approves one planned email. The rules run again now, so a case opened since then still blocks it."""
    hcp = world.hcp(hcp_id)
    allowed, why = authz.user_can(approver, "ApproveOutreach", "Outreach", hcp_id, {"country": hcp["country"]})
    ledger.append({"type": "authz", "user": approver["id"], "action": "ApproveOutreach", "allowed": allowed,
                   "reason": why, "hcp": hcp_id}, subject=hcp_id)
    if not allowed:
        raise Denied(f"{approver['name']} may not approve outreach for {hcp_id}. {why}")
    decision = _decision(hcp_id, touch_ref)
    touch = store.get("mi-touches", decision["id"])
    if decision["action"] != "propose":
        rules = [reason["rule"] for reason in decision["reasons"]]
        ledger.append({"type": "outreach_blocked", "touch": touch["id"], "hcp": hcp_id, "rules": rules}, subject=hcp_id)
        raise Blocked(f"{touch['id']} is held: {', '.join(rules)}")
    if touch["kind"] != "email":
        raise Blocked(f"{touch['id']} is a {touch['kind']}, and only emails go through delivery")
    block = store.content()[touch["content"]]
    message_id = delivery.deliver(hcp["email"], touch["summary"], block["text"], world.current_tenant())
    sent = touch | {"status": "done", "on": world.TODAY.isoformat(), "approved_by": approver["name"],
                    "delivery_id": message_id}
    store.put("mi-touches", sent)
    ledger.append({"type": "outreach_sent", "touch": touch["id"], "hcp": hcp_id, "approved_by": approver["id"],
                   "delivery_id": message_id, "block": [block["id"], block["version"]]}, subject=hcp_id)
    return sent
