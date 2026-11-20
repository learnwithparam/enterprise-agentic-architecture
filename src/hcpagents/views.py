"""The view each caller gets of a doctor.

The commercial view is read with the commercial database login. That login has no rights on the medical
or safety zones. So the view cannot show a case id, a case count or a safety note, even by mistake.
It learns only that contact is on hold. Cedar decides which view a person gets.
"""

from hcpagents import authz, db, hcp360, world

COMMERCIAL = "hcp_commercial"
MEDICAL_ACTION = "ViewMedicalZone"


def _kind(conn, kind: str) -> list[dict]:
    rows = conn.execute("SELECT doc FROM commercial.docs WHERE kind = %s ORDER BY id", (kind,))
    return [row["doc"] for row in rows]


def _content(conn) -> dict[str, dict]:
    rows = conn.execute("SELECT doc FROM public.docs WHERE kind = 'content'")
    return {row["doc"]["id"]: row["doc"] for row in rows}


def _holds(conn) -> list[dict]:
    return conn.execute("SELECT hcp_id, product, reason FROM shared.contact_hold").fetchall()


def _decide(touch: dict, hcp: dict, content: dict, holds: list[dict], done: list[dict]) -> dict:
    mine = [hold for hold in holds if hold["hcp_id"] == hcp["id"]]
    frozen = [hold for hold in mine if hold["reason"] == "safety_freeze"]
    cases = [{"product": hold["product"]} for hold in mine if hold["reason"] == "open_medical_case"]
    return hcp360.planned_decision(touch, hcp, content, cases, done, frozen=frozen)


def _country_then_name(hcp: dict) -> tuple:
    return hcp["country"], hcp["name"]


def _planned_on(touch: dict) -> str:
    return touch["on"]


SHOWN = ("id", "hcp", "on", "channel", "kind", "product", "promotional", "status", "content", "summary")
CASE_SUMMARY = "Medical information reply sent."


def _shown(touch: dict) -> dict:
    """Keep only the fields marketing may see. A touch from a case gets a plain summary, with no case id."""
    kept = {key: touch[key] for key in SHOWN if key in touch}
    if touch.get("case"):
        kept["summary"] = CASE_SUMMARY
    return kept


def commercial_summary() -> list[dict]:
    """One row for each doctor. Held is a count, with no reason."""
    with db.zone_session(COMMERCIAL) as conn:
        hcps, touches, content, holds = _kind(conn, "hcp"), _kind(conn, "touches"), _content(conn), _holds(conn)
    out = []
    for hcp in sorted(hcps, key=_country_then_name):
        mine = [touch for touch in touches if touch["hcp"] == hcp["id"]]
        done = [touch for touch in mine if touch["status"] == "done"]
        planned = [touch for touch in mine if touch["status"] == "planned"]
        held = sum(not _decide(touch, hcp, content, holds, done)["go"] for touch in planned)
        out.append({"id": hcp["id"], "name": hcp["name"], "country": hcp["country"], "specialty": hcp["specialty"],
                    "touches": len(done), "channels": len({touch["channel"] for touch in done}),
                    "planned": len(planned), "held": held})
    return out


def commercial_view(hcp_id: str) -> dict:
    """One doctor as marketing sees them. It has the touches and a yes or no on each plan."""
    with db.zone_session(COMMERCIAL) as conn:
        hcp = next((doc for doc in _kind(conn, "hcp") if doc["id"] == hcp_id), None)
        touches, content, holds = _kind(conn, "touches"), _content(conn), _holds(conn)
    mine = [touch for touch in touches if touch["hcp"] == hcp_id]
    done = [touch for touch in mine if touch["status"] == "done"]
    planned = sorted((touch for touch in mine if touch["status"] == "planned"), key=_planned_on)
    timeline = [_shown(touch) for touch in sorted(done, key=_planned_on, reverse=True)]
    return {"zone": "commercial", "hcp": hcp, "timeline": timeline,
            "planned": [_shown(touch) | {"decision": _decide(touch, hcp, content, holds, done)} for touch in planned]}


def view_for(user: dict, hcp_id: str) -> dict:
    """Cedar picks the view. Medical roles get the medical one and the rest get the commercial one."""
    allowed, _why = authz.user_can(user, MEDICAL_ACTION, "Hcp", hcp_id, {"country": world.current_tenant()})
    if allowed:
        return hcp360.view(hcp_id) | {"zone": "medical"}
    return commercial_view(hcp_id)
