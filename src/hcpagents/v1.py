"""The versioned API for machine clients, such as scripts and the hcp CLI (ADR 0028).

The /api routes serve the console and may change with it. The /v1 routes are the contract.
They only read and operate. Every route needs a token, a tenant and a rate limit.
Cedar checks every write.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from hcpagents import auth, authz, cases, db, events, ledger, releases, store, world

router = APIRouter(prefix="/v1")
WAITING = {"awaiting_review"}
POLL_SECONDS = 1.0


def current_user(request: Request) -> dict:
    return request.state.user


def _may(user: dict, action: str, resource_type: str, resource_id: str) -> None:
    allowed, reason = authz.user_can(user, action, resource_type, resource_id, {})
    if not allowed:
        raise HTTPException(403, reason)


def _by_id(case: dict) -> str:
    return case["id"]


@router.get("/cases")
def list_cases(user: dict = Depends(current_user)):
    return [cases.visible(case, user) for case in sorted(store.scan("mi-cases"), key=_by_id)]


@router.get("/cases/{case_id}")
def get_case(case_id: str, user: dict = Depends(current_user)):
    case = store.get("mi-cases", case_id)
    if case is None:
        raise HTTPException(404, "No such case")
    return cases.visible(case, user)


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/cases/{case_id}/events")
async def case_events(case_id: str, request: Request, user: dict = Depends(current_user), max_s: int = 60):
    """Stream the case history as it grows. It stops when no person is needed or max_s seconds pass."""
    if store.get("mi-cases", case_id) is None:
        raise HTTPException(404, "No such case")
    tenant = user["tenant"]

    async def stream():
        sent, waited = 0, 0.0
        while waited <= max_s and not await request.is_disconnected():
            with db.as_tenant(tenant):
                case = store.get("mi-cases", case_id)
            seen = cases.visible(case, user)
            for entry in seen.get("history", [])[sent:]:
                yield _frame("history", entry)
            sent = len(seen.get("history", []))
            if case["status"] not in WAITING:
                yield _frame("status", {"status": case["status"]})
                return
            await asyncio.sleep(POLL_SECONDS)
            waited += POLL_SECONDS
        yield _frame("timeout", {"status": case["status"]})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/dead-letters")
def dead_letters(user: dict = Depends(current_user)):
    _may(user, "ViewDeadLetters", "DeadLetter", "*")
    return events.dead_letters()


@router.post("/dead-letters/{dead_letter_id}/replay")
def replay(dead_letter_id: int, user: dict = Depends(current_user)):
    _may(user, "ReplayDeadLetter", "DeadLetter", str(dead_letter_id))
    try:
        return {"event_id": events.replay(dead_letter_id)}
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.get("/releases")
def release_trend(user: dict = Depends(current_user)):
    return releases.trend(user["tenant"])


@router.get("/releases/diff")
def release_diff(first: str = Query(alias="a"), second: str = Query(alias="b"), user: dict = Depends(current_user)):
    try:
        return releases.diff(first, second)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.post("/releases/{release}/promote")
def promote(release: str, user: dict = Depends(current_user)):
    """Make a release that passed the gate the baseline. Only compliance may."""
    _may(user, "PromoteRelease", "Release", release)
    try:
        releases.promote(release)
    except (LookupError, ValueError) as error:
        raise HTTPException(409, str(error)) from error
    return {"baseline": release}


def _change_access(user: dict, user_id: str, change, event: str) -> dict:
    """Revoke or reinstate one user of this tenant. Only compliance may. The ledger records who did it."""
    _may(user, "RevokeUser", "Ledger", "main")
    person = world.person(user_id)
    if person is None or person.get("tenant", db.DEFAULT_TENANT) != user["tenant"]:
        raise HTTPException(404, f"No user {user_id}")
    if user_id == user["id"]:
        raise HTTPException(409, "You cannot change your own access")
    change(user["tenant"], user_id)
    ledger.append({"type": event, "user": user_id, "by": user["id"]})
    return {"user": user_id, "status": event}


@router.post("/users/{user_id}/revoke")
def revoke(user_id: str, user: dict = Depends(current_user)):
    return _change_access(user, user_id, auth.revoke_user, "access_revoked")


@router.post("/users/{user_id}/reinstate")
def reinstate(user_id: str, user: dict = Depends(current_user)):
    return _change_access(user, user_id, auth.reinstate_user, "access_reinstated")
