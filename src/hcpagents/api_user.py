"""Small helpers that the console routes share."""

from fastapi import HTTPException, Request
from pydantic import BaseModel

from hcpagents import authz, cases


class Decision(BaseModel):
    note: str = ""


def current_user(request: Request) -> dict:
    """The user the middleware checked and put on this request."""
    return request.state.user


def denied(error: cases.Denied):
    raise HTTPException(403, str(error))


def require_compliance(user: dict) -> dict:
    allowed, reason = authz.user_can(user, "AuditLedger", "Ledger", "main", {})
    if not allowed:
        raise HTTPException(403, f"{user['name']} may not run ledger checks. {reason}")
    return user
