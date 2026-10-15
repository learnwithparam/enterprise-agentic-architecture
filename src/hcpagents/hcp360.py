"""HCP 360: one view of each doctor across the CRM, marketing, contact centre and portal, and the
rule that decides whether a planned touch may go. The decision is deterministic and explained."""

from datetime import date, timedelta

from hcpagents import store, world

WINDOW_DAYS = 30


def timeline(hcp_id: str) -> list[dict]:
    touches = [t for t in store.scan("mi-touches") if t["hcp"] == hcp_id and t["status"] == "done"]
    return sorted(touches, key=lambda t: t["on"], reverse=True)


def open_cases(hcp_id: str) -> list[dict]:
    done = {"sent", "declined", "rejected"}
    return [{"id": c["id"], "product": c["product"], "status": c["status"], "route": c["route"]}
            for c in store.scan("mi-cases") if c.get("hcp") and c["hcp"]["id"] == hcp_id and c["status"] not in done]


def planned_decision(p: dict, hcp: dict, content: dict, cases: list[dict], touches: list[dict], today: date = world.TODAY) -> dict:
    """May this planned touch go? Every reason it may not is listed; one is enough to hold it."""
    reasons = []
    consent_key = "email" if p["kind"] == "email" else "rep_visit" if p["kind"] == "rep_visit" else "phone"
    if not hcp["consent"].get(consent_key):
        reasons.append(f"No {consent_key.replace('_', ' ')} consent on record")
    if p.get("promotional"):
        cap = world.country(hcp["country"])["promo_cap_30d"]
        since = today - timedelta(days=WINDOW_DAYS)
        recent = [t for t in touches if t.get("promotional") and date.fromisoformat(t["on"][:10]) >= since]
        if len(recent) >= cap:
            reasons.append(f"{len(recent)} promotional touches in the last {WINDOW_DAYS} days; the {hcp['country']} cap is {cap}")
        blocking = [c for c in cases if c["product"] == p["product"]]
        if blocking:
            reasons.append(f"Open medical information case {blocking[0]['id']} on the same product; promotion waits until it closes")
    if p.get("content"):
        b = content.get(p["content"])
        why = world.why_not_current(b) if b else f"{p['content']} does not exist"
        if why:
            reasons.append(f"Content is not current: {why}")
        elif b["country"] != hcp["country"]:
            reasons.append(f"{b['id']} is approved for {b['country']}, not {hcp['country']}")
    return {"go": not reasons, "reasons": reasons}


def view(hcp_id: str) -> dict:
    hcp = store.get("mi-hcp", hcp_id)
    content = store.content()
    cases = open_cases(hcp_id)
    done = timeline(hcp_id)
    planned = [t for t in store.scan("mi-touches") if t["hcp"] == hcp_id and t["status"] == "planned"]
    return {
        "hcp": hcp,
        "timeline": done,
        "open_cases": cases,
        "planned": [p | {"decision": planned_decision(p, hcp, content, cases, done)} for p in sorted(planned, key=lambda p: p["on"])],
    }


def summary() -> list[dict]:
    content, all_touches, all_cases = store.content(), store.scan("mi-touches"), store.scan("mi-cases")
    out = []
    for hcp in sorted(store.scan("mi-hcp"), key=lambda h: (h["country"], h["name"])):
        done = [t for t in all_touches if t["hcp"] == hcp["id"] and t["status"] == "done"]
        cases = [{"id": c["id"], "product": c["product"]} for c in all_cases
                 if c.get("hcp") and c["hcp"]["id"] == hcp["id"] and c["status"] not in ("sent", "declined", "rejected")]
        planned = [t for t in all_touches if t["hcp"] == hcp["id"] and t["status"] == "planned"]
        held = sum(not planned_decision(p, hcp, content, cases, done)["go"] for p in planned)
        out.append({"id": hcp["id"], "name": hcp["name"], "country": hcp["country"], "specialty": hcp["specialty"],
                    "touches": len(done), "channels": len({t["channel"] for t in done}), "open_cases": len(cases),
                    "planned": len(planned), "held": held})
    return out
