"""A route that checks email copy against approved text."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hcpagents import factcheck
from hcpagents.api_user import current_user

router = APIRouter()


class Copy(BaseModel):
    text: str
    product: str
    country: str


@router.post("/api/content/check")
def check(body: Copy, _user: dict = Depends(current_user)):
    return factcheck.check_copy(body.text, body.product, body.country)
