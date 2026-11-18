"""Console routes for the proof screen and the design page. The tamper and reset demos are a second router, local only."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hcpagents import agents, authz, cases, events, graph, infra, ledger, observe, store, world
from hcpagents.api_user import current_user, denied, require_compliance
from hcpagents.aws import is_local

router = APIRouter()
demo_router = APIRouter()  # these break things on purpose, so only a local run gets them
EVAL_REPORT = world.ROOT / "evals" / "report.json"


class Autonomy(BaseModel):
    country: str
    enabled: bool


def autonomy_by_country() -> dict:
    return {country["code"]: cases.autonomy_setting(country["code"]) for country in world.products()["country"]}


@router.get("/api/autonomy")
def autonomy():
    return autonomy_by_country()


@router.post("/api/autonomy")
def set_autonomy(body: Autonomy, user: dict = Depends(current_user)):
    try:
        return cases.set_autonomy(body.country, body.enabled, user)
    except cases.Denied as error:
        denied(error)


@router.get("/api/proof")
def proof():
    rows = ledger.entries()
    report = None
    if EVAL_REPORT.exists():
        report = json.loads(EVAL_REPORT.read_text())
    all_cases = store.scan("mi-cases")
    return {
        "ledger": ledger.verify(), "recent": rows[-40:][::-1], "evals": report,
        "routes": observe.route_counts(), "queues": events.depth(),
        "spend": {"cases": len(all_cases), "cost_usd": round(sum(case.get("cost_usd", 0) for case in all_cases), 6),
                  "live_cases": sum(case.get("mode") == "live" for case in all_cases)},
    }


def _is_automatic_route(row: dict) -> bool:
    return row["entry"].get("type") == "routed" and row["entry"].get("route") != "send"


@demo_router.post("/api/proof/tamper")
def tamper(user: dict = Depends(current_user)):
    require_compliance(user)
    rows = ledger.entries()
    target = next((row for row in rows if _is_automatic_route(row)), None)
    if target is None:
        raise HTTPException(409, "Run a case that is not sent automatically first")
    changed = ledger.tamper(target["seq"])
    return {"tampered": changed, "by": user["name"], "verify": ledger.verify()}


@demo_router.post("/api/proof/restore")
def restore(user: dict = Depends(current_user)):
    require_compliance(user)
    check = ledger.verify()
    if not check["ok"]:
        ledger.restore(check["broken_at"])
    return ledger.verify()


@demo_router.post("/api/proof/delete-archive")
def delete_archive(user: dict = Depends(current_user)):
    require_compliance(user)
    return ledger.try_delete_archive(1)


@router.get("/api/architecture")
def architecture():
    return {"routing": [{"fact": fact, "value": value, "route": route, "why": why} for fact, value, route, why in graph.ROUTING],
            "send": {"route": graph.SEND[0], "why": graph.SEND[1]},
            "nodes": [{"node": node, "facts": list(facts)} for node, facts in graph.NODES],
            "asl": graph.asl(), "model": agents.MODEL, "prompt_version": agents.PROMPT_VERSION,
            "agents": {name: {"system": agent["system"], "tools": bool(agent.get("tools")), "max_turns": agent["max_turns"]}
                       for name, agent in agents.AGENTS.items()},
            "cedar": {file.name: file.read_text() for file in sorted((world.ROOT / "policies" / "cedar").glob("*.cedar"))}}


@demo_router.post("/api/reset")
def reset(user: dict = Depends(current_user)):
    allowed, reason = authz.user_can(user, "ResetDemo", "Ledger", "main", {})
    if not allowed:
        raise HTTPException(403, f"{user['name']} may not reset the platform. {reason}")
    infra.provision(reset=True)
    authz._store.cache_clear()
    authz._policy_file.cache_clear()
    return {"ok": True}


def routers() -> list[APIRouter]:
    """The routes to serve. The demo routes join them only when MI_ENV is local."""
    if is_local():
        return [router, demo_router]
    return [router]
