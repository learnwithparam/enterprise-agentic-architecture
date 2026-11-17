"""Console routes for the session, the inbox and the cases."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hcpagents import agents, auth, authz, cases, durable, ledger, store, world
from hcpagents.api_user import Decision, current_user, denied

router = APIRouter()


class Custom(BaseModel):
    hcp: str
    channel: str = "portal"
    text: str


class Signoff(BaseModel):
    password: str


def _by_id(case: dict) -> str:
    return case["id"]


@router.get("/api/session")
def session(user: dict = Depends(current_user)):
    mode = "replay"
    if agents.live():
        mode = "live"
    return {"user": user, "mode": mode, "model": agents.MODEL, "today": world.TODAY.isoformat()}


@router.get("/api/meta")
def meta():
    return {"people": world.people(), "products": world.products()["product"], "countries": world.products()["country"],
            "company": world.products()["company"], "routes": list(world.ROUTES)}


def _inquiry_row(inquiry: dict, done: dict, user: dict) -> dict:
    hcp = world.hcp(inquiry.get("hcp"))
    case = done.get(inquiry["id"])
    submitter = (inquiry.get("submitted_by") or "").split(",")[0]
    can_read, _ = authz.user_can(user, "ViewInquiryText", "Inquiry", inquiry["id"], {"submitter": submitter})
    text = None
    if can_read:
        text = inquiry["text"]
    sender, country = inquiry.get("sender"), inquiry.get("country")
    if hcp:
        sender, country = hcp["name"], hcp["country"]
    return {"id": inquiry["id"], "channel": inquiry["channel"], "received": inquiry["received"], "text": text,
            "from": sender, "country": country,
            "submitted_by": inquiry.get("submitted_by"), "eval_only": not inquiry.get("inbox"),
            "case": case and {"route": case["route"], "status": case["status"], "product": case["product"]}}


@router.get("/api/inquiries")
def inquiries(user: dict = Depends(current_user)):
    done = {case["id"]: case for case in store.scan("mi-cases")}
    rows = []
    for inquiry in world.inquiries():
        if not inquiry.get("inbox") and inquiry["id"] not in done:
            continue
        rows.append(_inquiry_row(inquiry, done, user))
    return rows


@router.post("/api/inquiries/{inquiry_id}/run")
async def run_inquiry(inquiry_id: str, user: dict = Depends(current_user)):
    if world.inquiry(inquiry_id) is None:
        raise HTTPException(404, "No such inquiry")
    try:
        case = await durable.run_inquiry(inquiry_id)
    except agents.MissingRecording as error:
        raise HTTPException(409, str(error)) from error
    except (agents.BudgetError, agents.ModelPolicyError) as error:
        raise HTTPException(402, str(error)) from error
    return cases.visible(case, user)


@router.post("/api/inquiries")
async def custom_inquiry(body: Custom, user: dict = Depends(current_user)):
    """A question typed in the console. It needs LIVE=1 because nothing is recorded for it."""
    if not agents.live():
        raise HTTPException(409, "Typed questions call the model. Restart the server with LIVE=1 to allow it.")
    number = len([case for case in store.scan("mi-cases") if case["id"].startswith("custom-")]) + 1
    inquiry = {"id": f"custom-{number}", "channel": body.channel, "hcp": body.hcp, "received": cases._now(),
               "text": body.text[:2000], "expect": None}
    try:
        case = await durable.run_inquiry(inquiry["id"], inquiry)
    except (agents.BudgetError, agents.ModelPolicyError) as error:
        raise HTTPException(402, str(error)) from error
    return cases.visible(case, user)


@router.get("/api/cases")
def list_cases(user: dict = Depends(current_user)):
    return [cases.visible(case, user) for case in sorted(store.scan("mi-cases"), key=_by_id)]


def _block_state(block_id: str) -> dict:
    block = store.get("mi-content", block_id)
    return {"version": block["version"], "status": block["status"], "current": world.is_current(block),
            "why_not": world.why_not_current(block)}


@router.get("/api/cases/{case_id}")
def get_case(case_id: str, user: dict = Depends(current_user)):
    case = store.get("mi-cases", case_id)
    if case is None:
        raise HTTPException(404, "No such case. Run the inquiry first.")
    case = cases.visible(case, user)
    if "redacted" not in case:
        case["ledger"] = [row | {"entry": row["entry"]} for row in ledger.entries(case_id, reveal=True)]
        segments = (case.get("draft") or {}).get("segments", [])
        case["content_now"] = {segment["block_id"]: _block_state(segment["block_id"]) for segment in segments}
    return case


@router.post("/api/cases/{case_id}/approve")
async def approve(case_id: str, body: Signoff, user: dict = Depends(current_user)):
    """The approver types their password again. That sign-in is their signature on the approval."""
    try:
        signature = auth.reauthenticate(user, body.password)
    except auth.Unauthenticated as error:
        raise HTTPException(403, str(error)) from error
    try:
        return await durable.decide(case_id, user, "approve", signature=signature)
    except cases.Denied as error:
        denied(error)


@router.post("/api/cases/{case_id}/reject")
async def reject(case_id: str, body: Decision, user: dict = Depends(current_user)):
    try:
        return await durable.decide(case_id, user, "reject", note=body.note or "No reason given")
    except cases.Denied as error:
        denied(error)
