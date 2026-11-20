"""Bind the signature to the reply. A change after signing stops the send, and a withdrawal closes the draft."""

import asyncio

import pytest

from hcpagents import approval, auth, case_review, case_send, cases, infra, world

pytestmark = pytest.mark.floci

BRANDT, WEBER = world.person("u-brandt"), world.person("u-weber")


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def signature():
    return auth.reauthenticate(BRANDT, auth.local_password(BRANDT["id"]))


def waiting_case():
    asyncio.run(cases.run("inq-103"))
    return case_review._load("inq-103")


def test_the_approval_keeps_a_digest_of_the_exact_reply():
    waiting_case()
    done = cases.approve("inq-103", BRANDT, signature())
    assert done["status"] == "sent"
    assert done["approval"]["draft_version"] == 1
    assert approval.problems(done) == []


def test_a_reply_changed_after_signing_is_not_sent():
    case = waiting_case()
    case.doc["approval"] = approval.bind(case.doc, signature())
    case.doc["draft"]["text"] += " Take a double dose."
    assert case_send.send(case, approved_by="Brandt") is False
    assert case.doc["status"] == "blocked_at_send"


def test_a_forged_signature_is_refused():
    case = waiting_case()
    case.doc["approval"] = approval.bind(case.doc, signature()) | {"kms_signature": "00" * 70}
    assert any("does not match the key" in line for line in approval.problems(case.doc))


def test_a_withdrawal_closes_the_draft_before_anyone_can_sign_it():
    waiting_case()
    cases.withdraw("VEL-DE-RENAL", WEBER, "Label update")
    with pytest.raises(cases.Denied):
        cases.approve("inq-103", BRANDT, signature())
