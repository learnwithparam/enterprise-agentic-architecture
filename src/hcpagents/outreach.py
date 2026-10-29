"""The outreach coordinator: the right next contact for each doctor, with no overlap (ADR 0023).

It reads HCP 360 and decides for every planned touch whether it may be proposed to a human. It acts alone
only to hold a touch, never to send one: `propose` means a rep or marketer still has to approve. Every
reason is traced to the rule that fired and the case or touch behind it, and each hold is written to the
ledger so Compliance can see why a doctor was not contacted.
"""

from hcpagents import hcp360, ledger, store, supervisor


def coordinate(hcp_id: str) -> list[dict]:
    """One decision per planned touch, oldest first: {id, action: propose|hold, reasons: [{rule, why, source}]}."""
    view = hcp360.view(hcp_id)
    cases = view["open_cases"]
    held = {p["id"]: [_reason(rule, why, cases, view["freezes"]) for rule, why in zip(p["decision"]["rules"], p["decision"]["reasons"], strict=True)]
            for p in view["planned"] if not p["decision"]["go"]}
    clear = [p for p in view["planned"] if p["decision"]["go"]]
    for loser, winner in supervisor.arbitrate(clear).items():
        held[loser] = [{"rule": "overlap", "why": f"Yields to {winner}, planned within {supervisor.OVERLAP_DAYS} days", "source": winner}]
    return [{"id": p["id"], "on": p["on"], "action": "hold" if p["id"] in held else "propose",
             "reasons": held.get(p["id"], [])} for p in view["planned"]]


def _reason(rule: str, why: str, cases: list[dict], freezes: list[dict]) -> dict:
    source = (cases[0]["id"] if rule == "open_medical_case" and cases
              else freezes[0]["interaction"] if rule == "safety_freeze" and freezes else None)
    return {"rule": rule, "why": why, "source": source}


def run(hcp_id: str) -> list[dict]:
    """Coordinate, store the decision on the touch, and ledger every hold."""
    decisions = coordinate(hcp_id)
    for d in decisions:
        touch = store.get("mi-touches", d["id"])
        if touch.get("coordinator") != d["action"]:
            store.put("mi-touches", touch | {"coordinator": d["action"], "reasons": d["reasons"]})
            if d["action"] == "hold":
                ledger.append({"type": "outreach_hold", "agent": "outreach-coordinator", "touch": d["id"],
                               "hcp": hcp_id, "rules": [r["rule"] for r in d["reasons"]]})
    return decisions
