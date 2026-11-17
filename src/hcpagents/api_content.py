"""Console routes for content, people and releases."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from hcpagents import cases, hcp360, insight, outreach, releases, store, world
from hcpagents.api_user import Decision, current_user, denied

router = APIRouter()


def _block_order(block: dict) -> tuple:
    return (block["product"], block["country"], block["id"])


@router.get("/api/content")
def content():
    rows = []
    for block in sorted(store.content().values(), key=_block_order):
        rows.append(block | {"current": world.is_current(block), "why_not": world.why_not_current(block)})
    return rows


@router.post("/api/content/{block_id}/withdraw")
def withdraw(block_id: str, body: Decision, user: dict = Depends(current_user)):
    if store.get("mi-content", block_id) is None:
        raise HTTPException(404, "No such block")
    try:
        return cases.withdraw(block_id, user, body.note or "Withdrawn by content owner")  # the steward checks the drafts again
    except cases.Denied as error:
        denied(error)


@router.get("/api/hcps")
def hcps():
    return hcp360.summary()


@router.get("/api/hcps/{hcp_id}")
def hcp(hcp_id: str):
    if store.get("mi-hcp", hcp_id) is None:
        raise HTTPException(404, "No such HCP")
    return hcp360.view(hcp_id)


@router.get("/api/insights")
def insights(since: datetime | None = None):
    return insight.digest(since)


@router.get("/api/releases")
def release_trend():
    return releases.trend(world.current_tenant())


@router.get("/api/monitors")
def monitors():
    """What live cases did under each release. Use it to compare a canary with the baseline."""
    return releases.online(world.current_tenant())


@router.get("/api/hcps/{hcp_id}/outreach")
def hcp_outreach(hcp_id: str):
    if store.get("mi-hcp", hcp_id) is None:
        raise HTTPException(404, "No such HCP")
    return outreach.coordinate(hcp_id)


@router.post("/api/hcps/{hcp_id}/erase")
def erase_hcp(hcp_id: str, user: dict = Depends(current_user)):
    try:
        return cases.erase_person(hcp_id, user)
    except cases.Denied as error:
        denied(error)
