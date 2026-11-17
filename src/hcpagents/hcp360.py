"""HCP 360: one view of each doctor from the CRM, marketing, contact centre and portal.

It also holds the rule that decides if a planned touch may go. The decision is fixed and it explains itself.
"""

from datetime import date, timedelta

from hcpagents import identity, store, world

WINDOW_DAYS = 30
CLOSED_STATUSES = ("sent", "declined", "rejected")


def _planned_on(touch: dict):
    return touch["on"]


def timeline(hcp_id: str) -> list[dict]:
    touches = [touch for touch in store.scan("mi-touches") if touch["hcp"] == hcp_id and touch["status"] == "done"]
    return sorted(touches, key=_planned_on, reverse=True)


def open_cases(hcp_id: str) -> list[dict]:
    done = set(CLOSED_STATUSES)
    return [{"id": case["id"], "product": case["product"], "status": case["status"], "route": case["route"]}
            for case in store.scan("mi-cases")
            if case.get("hcp") and case["hcp"]["id"] == hcp_id and case["status"] not in done]


def freezes(hcp_id: str) -> list[dict]:
    """Contact freezes that the sentinel opened on this doctor. Only a human can lift one."""
    return [freeze for freeze in store.scan("mi-freezes") if freeze["hcp"] == hcp_id]


def _consent_key(kind: str) -> str:
    if kind == "email":
        return "email"
    if kind == "rep_visit":
        return "rep_visit"
    return "phone"


def _content_reason(planned_touch: dict, hcp: dict, content: dict) -> tuple[str, str] | None:
    block = content.get(planned_touch["content"])
    if block:
        why = world.why_not_current(block)
    else:
        why = f"{planned_touch['content']} does not exist"
    if why:
        return f"Content is not current: {why}", "content_not_current"
    if block["country"] != hcp["country"]:
        return f"{block['id']} is approved for {block['country']}, not {hcp['country']}", "content_country"
    return None


def planned_decision(planned_touch: dict, hcp: dict, content: dict, cases: list[dict], touches: list[dict],
                     today: date = world.TODAY, frozen: list[dict] = ()) -> dict:
    """May this planned touch go? Every reason it may not is listed. One is enough to hold it."""
    reasons, rules = [], []
    if frozen:
        reasons.append(f"Contact is frozen after a possible safety signal ({frozen[0]['case']}); a human lifts the freeze")
        rules.append("safety_freeze")
    consent_key = _consent_key(planned_touch["kind"])
    if not hcp["consent"].get(consent_key):
        reasons.append(f"No {consent_key.replace('_', ' ')} consent on record")
        rules.append("consent")
    if planned_touch.get("promotional"):
        cap = world.country(hcp["country"])["promo_cap_30d"]
        since = today - timedelta(days=WINDOW_DAYS)
        recent = [touch for touch in touches
                  if touch.get("promotional") and date.fromisoformat(touch["on"][:10]) >= since]
        if len(recent) >= cap:
            reasons.append(f"{len(recent)} promotional touches in the last {WINDOW_DAYS} days; the {hcp['country']} cap is {cap}")
            rules.append("frequency_cap")
        blocking = [case for case in cases if case["product"] == planned_touch["product"]]
        if blocking:
            reasons.append(f"Open medical information case {blocking[0]['id']} on the same product; promotion waits until it closes")
            rules.append("open_medical_case")
    if planned_touch.get("content"):
        content_reason = _content_reason(planned_touch, hcp, content)
        if content_reason:
            reasons.append(content_reason[0])
            rules.append(content_reason[1])
    return {"go": not reasons, "reasons": reasons, "rules": rules}


def view(hcp_id: str) -> dict:
    hcp = store.get("mi-hcp", hcp_id)
    content = store.content()
    cases = open_cases(hcp_id)
    done, frozen = timeline(hcp_id), freezes(hcp_id)
    planned = [touch for touch in store.scan("mi-touches") if touch["hcp"] == hcp_id and touch["status"] == "planned"]
    return {
        "hcp": hcp,
        "timeline": done,
        "interactions": identity.interactions(hcp_id),
        "freezes": frozen,
        "open_cases": cases,
        "planned": [touch | {"decision": planned_decision(touch, hcp, content, cases, done, frozen=frozen)}
                    for touch in sorted(planned, key=_planned_on)],
    }


def _name_order(hcp: dict) -> tuple:
    return hcp["country"], hcp["name"]


def summary() -> list[dict]:
    content, all_touches, all_cases = store.content(), store.scan("mi-touches"), store.scan("mi-cases")
    all_freezes = store.scan("mi-freezes")
    out = []
    for hcp in sorted(store.scan("mi-hcp"), key=_name_order):
        done = [touch for touch in all_touches if touch["hcp"] == hcp["id"] and touch["status"] == "done"]
        cases = [{"id": case["id"], "product": case["product"]} for case in all_cases
                 if case.get("hcp") and case["hcp"]["id"] == hcp["id"] and case["status"] not in CLOSED_STATUSES]
        planned = [touch for touch in all_touches if touch["hcp"] == hcp["id"] and touch["status"] == "planned"]
        frozen = [freeze for freeze in all_freezes if freeze["hcp"] == hcp["id"]]
        held = sum(not planned_decision(touch, hcp, content, cases, done, frozen=frozen)["go"] for touch in planned)
        out.append({"id": hcp["id"], "name": hcp["name"], "country": hcp["country"], "specialty": hcp["specialty"],
                    "touches": len(done), "channels": len({touch["channel"] for touch in done}),
                    "open_cases": len(cases), "planned": len(planned), "held": held})
    return out
