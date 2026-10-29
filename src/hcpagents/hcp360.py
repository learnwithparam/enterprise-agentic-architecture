"""HCP 360: one view of each doctor across the CRM, marketing, contact centre and portal, and the
rule that decides whether a planned touch may go. The decision is deterministic and explained."""

from datetime import date, timedelta

from hcpagents import identity, store, world

WINDOW_DAYS = 30


def timeline(hcp_id: str) -> list[dict]:
    touches = [t for t in store.scan("mi-touches") if t["hcp"] == hcp_id and t["status"] == "done"]
    return sorted(touches, key=lambda t: t["on"], reverse=True)


def open_cases(hcp_id: str) -> list[dict]:
    done = {"sent", "declined", "rejected"}
    return [{"id": c["id"], "product": c["product"], "status": c["status"], "route": c["route"]}
            for c in store.scan("mi-cases") if c.get("hcp") and c["hcp"]["id"] == hcp_id and c["status"] not in done]


def freezes(hcp_id: str) -> list[dict]:
    """Contact freezes the safety sentinel opened on this doctor. Only a human lifts one."""
    return [f for f in store.scan("mi-freezes") if f["hcp"] == hcp_id]


def planned_decision(p: dict, hcp: dict, content: dict, cases: list[dict], touches: list[dict],
                     today: date = world.TODAY, frozen: list[dict] = ()) -> dict:
    """May this planned touch go? Every reason it may not is listed; one is enough to hold it."""
    reasons, rules = [], []
    if frozen:
        reasons.append(f"Contact is frozen after a possible safety signal ({frozen[0]['case']}); a human lifts the freeze")
        rules.append("safety_freeze")
    consent_key = "email" if p["kind"] == "email" else "rep_visit" if p["kind"] == "rep_visit" else "phone"
    if not hcp["consent"].get(consent_key):
        reasons.append(f"No {consent_key.replace('_', ' ')} consent on record")
        rules.append("consent")
    if p.get("promotional"):
        cap = world.country(hcp["country"])["promo_cap_30d"]
        since = today - timedelta(days=WINDOW_DAYS)
        recent = [t for t in touches if t.get("promotional") and date.fromisoformat(t["on"][:10]) >= since]
        if len(recent) >= cap:
            reasons.append(f"{len(recent)} promotional touches in the last {WINDOW_DAYS} days; the {hcp['country']} cap is {cap}")
            rules.append("frequency_cap")
        blocking = [c for c in cases if c["product"] == p["product"]]
        if blocking:
            reasons.append(f"Open medical information case {blocking[0]['id']} on the same product; promotion waits until it closes")
            rules.append("open_medical_case")
    if p.get("content"):
        b = content.get(p["content"])
        why = world.why_not_current(b) if b else f"{p['content']} does not exist"
        if why:
            reasons.append(f"Content is not current: {why}")
            rules.append("content_not_current")
        elif b["country"] != hcp["country"]:
            reasons.append(f"{b['id']} is approved for {b['country']}, not {hcp['country']}")
            rules.append("content_country")
    return {"go": not reasons, "reasons": reasons, "rules": rules}


def view(hcp_id: str) -> dict:
    hcp = store.get("mi-hcp", hcp_id)
    content = store.content()
    cases = open_cases(hcp_id)
    done, frozen = timeline(hcp_id), freezes(hcp_id)
    planned = [t for t in store.scan("mi-touches") if t["hcp"] == hcp_id and t["status"] == "planned"]
    return {
        "hcp": hcp,
        "timeline": done,
        "interactions": identity.interactions(hcp_id),
        "freezes": frozen,
        "open_cases": cases,
        "planned": [p | {"decision": planned_decision(p, hcp, content, cases, done, frozen=frozen)} for p in sorted(planned, key=lambda p: p["on"])],
    }


def summary() -> list[dict]:
    content, all_touches, all_cases = store.content(), store.scan("mi-touches"), store.scan("mi-cases")
    all_freezes = store.scan("mi-freezes")
    out = []
    for hcp in sorted(store.scan("mi-hcp"), key=lambda h: (h["country"], h["name"])):
        done = [t for t in all_touches if t["hcp"] == hcp["id"] and t["status"] == "done"]
        cases = [{"id": c["id"], "product": c["product"]} for c in all_cases
                 if c.get("hcp") and c["hcp"]["id"] == hcp["id"] and c["status"] not in ("sent", "declined", "rejected")]
        planned = [t for t in all_touches if t["hcp"] == hcp["id"] and t["status"] == "planned"]
        frozen = [f for f in all_freezes if f["hcp"] == hcp["id"]]
        held = sum(not planned_decision(p, hcp, content, cases, done, frozen=frozen)["go"] for p in planned)
        out.append({"id": hcp["id"], "name": hcp["name"], "country": hcp["country"], "specialty": hcp["specialty"],
                    "touches": len(done), "channels": len({t["channel"] for t in done}), "open_cases": len(cases),
                    "planned": len(planned), "held": held})
    return out
