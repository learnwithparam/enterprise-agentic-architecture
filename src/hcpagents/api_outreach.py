"""Console route for approving one planned touch."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hcpagents import outreach, world
from hcpagents.api_user import current_user

router = APIRouter()


class Approval(BaseModel):
    touch: str


@router.post("/api/outreach/{hcp_id}/approve")
def approve_outreach(hcp_id: str, body: Approval, user: dict = Depends(current_user)):
    """The approver is the signed-in user. The rules run again before anything is sent."""
    if world.hcp(hcp_id) is None:
        raise HTTPException(404, "No such doctor")
    try:
        return outreach.approve(hcp_id, body.touch, user)
    except outreach.Denied as error:
        raise HTTPException(403, str(error)) from error
    except outreach.Blocked as error:
        raise HTTPException(409, str(error)) from error
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
