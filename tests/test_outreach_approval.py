"""A human approves a planned email. The rules run again at send time, so a case opened since then still blocks it."""

import httpx
import pytest
from fastapi.testclient import TestClient

from hcpagents import api, api_outreach, aws, ledger, outreach, store
from tests.test_flow import BECKER, BRANDT, as_user, fresh  # noqa: F401 - fresh is an autouse fixture

pytestmark = pytest.mark.floci


TOUCH_ID = "plan-kaya-clear"
CLEAR_EMAIL = {"id": TOUCH_ID, "hcp": "hcp-kaya", "on": "2026-10-10", "channel": "marketing", "kind": "email", "product": "VEL",
                 "promotional": True, "status": "planned", "content": "VEL-DE-DOSE", "summary": "Email campaign: Veltrona dosing."}
OPEN_CASE = {"id": "case-open", "hcp": {"id": "hcp-kaya"}, "product": "VEL", "status": "awaiting_review", "route": "review"}


@pytest.fixture(autouse=True)
def planned_email(fresh):  # noqa: F811 - runs after the reset
    # The seed email for Dr. Kaya is held by the German frequency cap on purpose. Here the cap is cleared, so only the case can hold it.
    for touch in store.scan("mi-touches"):
        if touch["hcp"] == "hcp-kaya" and touch.get("promotional"):
            store.put("mi-touches", {**touch, "promotional": False})
    store.put("mi-touches", CLEAR_EMAIL)

def outbox() -> dict[str, dict]:
    rows = httpx.get(f"{aws.ENDPOINT}/_aws/ses", timeout=10).json()["messages"]
    return {row["Id"]: row for row in rows}


def test_approval_sends_the_approved_text_records_the_touch_and_writes_the_ledger():
    sent = outreach.approve("hcp-kaya", TOUCH_ID, BECKER)
    block = store.content()["VEL-DE-DOSE"]
    message = outbox()[sent["delivery_id"]]
    assert message["Body"]["text_part"] == block["text"]
    assert message["Destination"]["ToAddresses"] == ["kaya@hcp.example"]
    assert store.get("mi-touches", TOUCH_ID)["status"] == "done"
    assert any(row["entry"]["type"] == "outreach_sent" and row["entry"]["delivery_id"] == sent["delivery_id"]
               for row in ledger.entries())


def test_an_open_medical_case_blocks_an_approved_touch():
    store.put("mi-cases", OPEN_CASE)
    before = set(outbox())
    with pytest.raises(outreach.Blocked, match="open_medical_case"):
        outreach.approve("hcp-kaya", TOUCH_ID, BECKER)
    assert set(outbox()) == before
    assert store.get("mi-touches", TOUCH_ID)["status"] == "planned"


def test_only_a_rep_in_the_doctors_country_may_approve():
    before = set(outbox())
    with pytest.raises(outreach.Denied, match="Verified Permissions"):
        outreach.approve("hcp-kaya", TOUCH_ID, BRANDT)  # a reviewer is not a field rep
    with pytest.raises(outreach.Denied, match="Verified Permissions"):
        outreach.approve("hcp-kaya", TOUCH_ID, {**BECKER, "country": "US"})  # a rep from another country
    assert set(outbox()) == before


def test_the_approval_route_sends_and_refuses_with_the_right_status():
    assert any(route.path == "/api/outreach/{hcp_id}/approve" for route in api_outreach.router.routes)
    app = api.app
    app.include_router(api_outreach.router)
    client = TestClient(app)
    refused = client.post("/api/outreach/hcp-kaya/approve", headers=as_user("u-brandt"), json={"touch": TOUCH_ID})
    assert refused.status_code == 403
    store.put("mi-cases", OPEN_CASE)
    held = client.post("/api/outreach/hcp-kaya/approve", headers=as_user("u-becker"), json={"touch": TOUCH_ID})
    assert held.status_code == 409
