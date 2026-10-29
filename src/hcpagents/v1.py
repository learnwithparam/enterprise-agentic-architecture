"""The versioned API for machine clients: scripts, the hcp CLI and other systems (ADR 0028).

/api serves the console and may change with it. /v1 is the contract: it is read and operate only,
every route is behind the same token, tenant scope and rate limit, and writes are Cedar checked.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from hcpagents import authz, cases, db, events, releases, store

router = APIRouter(prefix="/v1")
WAITING = {"awaiting_review"}
POLL_S = 1.0


def user(request: Request) -> dict:
    return request.state.user


def _may(u: dict, action: str, resource_type: str, resource_id: str) -> None:
    ok, why = authz.user_can(u, action, resource_type, resource_id, {})
    if not ok:
        raise HTTPException(403, why)


@router.get("/cases")
def list_cases(u: dict = Depends(user)):
    return [cases.visible(c, u) for c in sorted(store.scan("mi-cases"), key=lambda c: c["id"])]


@router.get("/cases/{case_id}")
def get_case(case_id: str, u: dict = Depends(user)):
    d = store.get("mi-cases", case_id)
    if d is None:
        raise HTTPException(404, "No such case")
    return cases.visible(d, u)


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/cases/{case_id}/events")
async def case_events(case_id: str, request: Request, u: dict = Depends(user), max_s: int = 60):
    """Server-sent events: the case's history as it grows, until a person is no longer needed or `max_s` passes."""
    if store.get("mi-cases", case_id) is None:
        raise HTTPException(404, "No such case")
    tenant = u["tenant"]

    async def stream():
        sent, waited = 0, 0.0
        while waited <= max_s and not await request.is_disconnected():
            with db.as_tenant(tenant):
                d = store.get("mi-cases", case_id)
            seen = cases.visible(d, u)
            for h in seen.get("history", [])[sent:]:
                yield _frame("history", h)
            sent = len(seen.get("history", []))
            if d["status"] not in WAITING:
                yield _frame("status", {"status": d["status"]})
                return
            await asyncio.sleep(POLL_S)
            waited += POLL_S
        yield _frame("timeout", {"status": d["status"]})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/dead-letters")
def dead_letters(u: dict = Depends(user)):
    _may(u, "ViewDeadLetters", "DeadLetter", "*")
    return events.dead_letters()


@router.post("/dead-letters/{dead_letter_id}/replay")
def replay(dead_letter_id: int, u: dict = Depends(user)):
    _may(u, "ReplayDeadLetter", "DeadLetter", str(dead_letter_id))
    try:
        return {"event_id": events.replay(dead_letter_id)}
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/releases")
def release_trend(u: dict = Depends(user)):
    return releases.trend(u["tenant"])


@router.get("/releases/diff")
def release_diff(a: str, b: str, u: dict = Depends(user)):
    try:
        return releases.diff(a, b)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/releases/{release}/promote")
def promote(release: str, u: dict = Depends(user)):
    """Make a release that passed the gate the baseline. Only compliance may."""
    _may(u, "PromoteRelease", "Release", release)
    try:
        releases.promote(release)
    except (LookupError, ValueError) as e:
        raise HTTPException(409, str(e)) from e
    return {"baseline": release}
