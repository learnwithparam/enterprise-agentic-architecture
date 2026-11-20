"""A signature covers one exact reply. If any part of it moves after signing, nothing is sent."""

import asyncio

import pytest

from hcpagents import approval, auth, case_review, case_send, cases, infra, ledger, store, world

pytestmark = pytest.mark.floci

BRANDT, WEBER = world.person("u-brandt"), world.person("u-weber")


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def sign(user):
    return auth.reauthenticate(user, auth.local_password(user["id"]))


def waiting_case():
    asyncio.run(cases.run("inq-103"))
    return case_review._load("inq-103")


def signed_case():
    case = waiting_case()
    case.doc["approval"] = approval.bind(case.doc, sign(BRANDT))
    return case


def types(case_id):
    return [row["entry"]["type"] for row in ledger.entries(case_id)]


def test_an_approval_keeps_the_digest_the_release_and_the_draft_version():
    waiting_case()
    done = cases.approve("inq-103", BRANDT, sign(BRANDT))
    record = done["approval"]
    assert done["status"] == "sent" and record["release"] == done["release"] and record["draft_version"] == 1
    assert record["digest"] == approval.digest(done["draft"]["text"], done["draft"]["segments"], done["hcp"]["id"],
                                               done["country"], record["release"], 1)
    assert approval.problems(done) == []
    sent = next(row["entry"] for row in ledger.entries("inq-103") if row["entry"]["type"] == "reply_sent")
    assert sent["approval_digest"] == record["digest"]


def test_a_reply_changed_after_signing_is_never_sent_and_the_ledger_says_so():
    case = signed_case()
    case.doc["draft"]["text"] += " Take a double dose."
    assert case_send.send(case, approved_by="Brandt") is False
    assert case.doc["status"] == "blocked_at_send"
    assert "send_blocked" in types("inq-103")
    assert any("changed after it was signed" in line for line in case.doc["history"][-1]["detail"])


def test_a_block_version_changed_after_signing_is_never_sent():
    case = signed_case()
    case.doc["draft"]["segments"][0] = case.doc["draft"]["segments"][0] | {"version": 99}
    assert any("changed after it was signed" in line for line in approval.problems(case.doc))


def test_a_draft_written_again_after_signing_is_never_sent():
    case = signed_case()
    case.doc["draft_version"] += 1
    assert any("written again" in line for line in approval.problems(case.doc))


def test_a_signature_that_does_not_match_the_key_is_refused():
    case = signed_case()
    case.doc["approval"]["kms_signature"] = "00" * 70
    assert any("does not match the key" in line for line in approval.problems(case.doc))


def test_a_send_with_no_signature_bound_to_the_draft_is_blocked():
    case = waiting_case()
    assert case_send.send(case, approved_by="Brandt") is False
    assert any("no approval" in line for line in case.doc["history"][-1]["detail"])


def test_an_automatic_reply_needs_no_approval():
    assert asyncio.run(cases.run("inq-101"))["status"] == "sent"


def test_a_rejection_is_on_the_ledger():
    waiting_case()
    cases.reject("inq-103", BRANDT, "wrong product")
    assert "rejected" in types("inq-103")


def test_a_draft_lists_each_block_it_uses_so_a_withdrawal_finds_it_without_a_scan():
    waiting_case()
    found = store.scan_prefix("mi-draft-sources", "VEL-DE-RENAL:")
    assert [source["case"] for source in found] == ["inq-103"]
    assert store.scan_prefix("mi-draft-sources", "VEL-US-DOSE:") == []


def test_a_withdrawal_closes_the_draft_before_a_reviewer_can_sign_it():
    waiting_case()
    cases.withdraw("VEL-DE-RENAL", WEBER, "Label update")
    with pytest.raises(cases.Denied):
        cases.approve("inq-103", BRANDT, sign(BRANDT))
    assert "draft_invalidated" in types("inq-103")
