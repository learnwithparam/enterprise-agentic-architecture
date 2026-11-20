"""A reply that passes the send check leaves as a real email. The SES outbox holds exactly what was sent."""

import httpx
import pytest

from hcpagents import aws, cases, delivery, ledger
from tests.test_flow import BRANDT, RAMAN, WEBER, fresh, run, sign  # noqa: F401 - fresh is an autouse fixture

pytestmark = pytest.mark.floci


def outbox() -> dict[str, dict]:
    rows = httpx.get(f"{aws.ENDPOINT}/_aws/ses", timeout=10).json()["messages"]
    return {row["Id"]: row for row in rows}


def types(case_id: str) -> list[str]:
    return [row["entry"]["type"] for row in ledger.entries(case_id)]


def test_the_outbox_holds_the_exact_grounded_reply_and_the_ledger_names_the_message():
    before = set(outbox())
    doc = run("inq-101")
    message = outbox()[doc["delivery_id"]]
    assert doc["status"] == "sent" and doc["delivery_id"] not in before
    assert message["Body"]["text_part"] == doc["draft"]["text"]
    assert message["Destination"]["ToAddresses"] == ["kaya@hcp.example"]
    sent = next(row["entry"] for row in ledger.entries("inq-101") if row["entry"]["type"] == "reply_sent")
    assert sent["delivery_id"] == doc["delivery_id"]


def test_a_block_withdrawn_before_the_send_sends_nothing():
    cases.set_autonomy("DE", False, RAMAN)
    doc = run("inq-101")
    before = set(outbox())
    assert cases.withdraw(doc["draft"]["segments"][0]["block_id"], WEBER, "Label update")["invalidated"] == ["inq-101"]
    with pytest.raises(cases.Denied):
        cases.approve("inq-101", BRANDT, sign(BRANDT))
    assert set(outbox()) == before


def test_a_reply_to_a_doctor_who_asked_is_sent_even_without_marketing_consent():
    run("inq-103")
    before = set(outbox())
    doc = cases.approve("inq-103", BRANDT, sign(BRANDT))
    assert doc["status"] == "sent" and doc["delivery_id"]
    assert set(outbox()) - before == {doc["delivery_id"]}


def test_a_delivery_that_fails_is_not_marked_sent(monkeypatch):
    def broken(*_args):
        raise RuntimeError("SES is down")

    cases.set_autonomy("DE", False, RAMAN)
    run("inq-101")
    monkeypatch.setattr(delivery, "deliver", broken)
    doc = cases.approve("inq-101", BRANDT, sign(BRANDT))
    assert doc["status"] == "delivery_failed" and "sent_at" not in doc
    assert "delivery_failed" in types("inq-101") and "reply_sent" not in types("inq-101")
