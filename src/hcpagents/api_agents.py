"""Console routes for the agent list and the ideas to improve them."""

from fastapi import APIRouter, Depends, HTTPException

from hcpagents import authz, gateway, guardian, improver, store, world
from hcpagents.api_proof import autonomy_by_country
from hcpagents.api_user import current_user

router = APIRouter()


def _spend_of(agent: dict, spend: dict) -> dict:
    calls, cost = 0, 0.0
    if agent["id"] in spend:
        calls = int(spend[agent["id"]]["calls"])
        cost = float(spend[agent["id"]]["cost_usd"])
    return agent | {"calls": calls, "cost_usd": cost}


@router.get("/api/agents")
def agents_page():
    """Each agent with its cost to this tenant. It also shows what each country allows."""
    spend = {row["agent"]: row for row in gateway.spend_by(world.current_tenant(), "agent")}
    return {"agents": [_spend_of(agent, spend) for agent in world.agents()],
            "autonomy": autonomy_by_country(),
            "guardian": guardian.override_rates(), "proposals": proposals()}


@router.get("/api/guardian")
def guardian_status():
    return guardian.override_rates()


@router.get("/api/proposals")
def proposals():
    return [proposal for proposal in store.scan("mi-proposals") if proposal["kind"] != "correction"]


@router.post("/api/proposals/refresh")
def refresh_proposals(user: dict = Depends(current_user)):
    ok, why = authz.user_can(user, "RefreshProposals", "Proposal", "*", {})
    if not ok:
        raise HTTPException(403, why)
    return improver.propose()
