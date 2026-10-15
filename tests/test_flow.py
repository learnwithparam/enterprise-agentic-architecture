"""End to end on Floci, in replay: the moments a human stays in control, and the proof Compliance checks."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, cases, hcp360, infra, ledger, store, world

pytestmark = pytest.mark.floci

BRANDT, HALE, WEBER, BECKER, RAMAN, LIND = (world.person(u) for u in ("u-brandt", "u-hale", "u-weber", "u-becker", "u-raman", "u-lind"))


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def run(i):
    return asyncio.run(cases.run(i))


def test_auto_send_records_a_touch_on_the_hcp_timeline():
    d = run("inq-101")
    assert d["status"] == "sent" and d["send_check"]["grounded"]
    assert any(t.get("case") == "inq-101" for t in hcp360.timeline("hcp-kaya"))


def test_reviewer_approves_only_in_their_own_country():
    run("inq-103")
    with pytest.raises(cases.Denied):
        cases.approve("inq-103", HALE)
    assert cases.approve("inq-103", BRANDT)["status"] == "sent"


def test_nobody_approves_on_a_pharmacovigilance_case():
    d = run("inq-105")
    assert d["draft"] is None and d["status"] == "with_pharmacovigilance"
    # Hale reviews in the US, the case's country, so only the pharmacovigilance forbid can refuse him here.
    with pytest.raises(cases.Denied, match="may not ApproveReply on inq-105. Verified Permissions: DENY"):
        cases.approve("inq-105", HALE)


def test_withdrawn_content_invalidates_the_draft_and_blocks_the_send():
    run("inq-103")
    with pytest.raises(cases.Denied):
        cases.withdraw("VEL-DE-RENAL", BECKER, "not my job")
    assert cases.withdraw("VEL-DE-RENAL", WEBER, "Label update")["cases"] == ["inq-103"]
    d = cases.approve("inq-103", BRANDT)
    assert d["status"] == "blocked_at_send"
    assert any("withdrawn" in p for p in d["send_check"]["problems"])


def test_compliance_kill_switch_stops_automatic_replies():
    with pytest.raises(cases.Denied):
        cases.set_autonomy("DE", False, BRANDT)
    cases.set_autonomy("DE", False, RAMAN)
    assert run("inq-101")["route"] == "review"


def test_ledger_detects_tampering_and_the_archive_refuses_deletion():
    run("inq-105")
    assert ledger.verify()["ok"]
    seq = next(r["seq"] for r in ledger.entries("inq-105") if r["entry"]["type"] == "routed")
    ledger.tamper(seq)
    v = ledger.verify()
    assert not v["ok"] and v["broken_at"] == seq
    assert ledger.try_delete_archive(seq)["deleted"] is False
    ledger.restore(seq)
    assert ledger.verify()["ok"]


def test_every_tool_call_is_on_the_ledger_with_its_guard_decision():
    run("inq-110")
    calls = [r["entry"] for r in ledger.entries("inq-110") if r["entry"]["type"] == "tool_call"]
    assert calls and all(c["allowed"] and c["input"]["country"] == "US" for c in calls if "country" in c["input"])


def test_planned_promotion_is_held_over_the_frequency_cap_and_open_cases():
    run("inq-103")
    kaya = {p["id"]: p["decision"] for p in hcp360.view("hcp-kaya")["planned"]}
    assert not kaya["plan-kaya-email"]["go"]
    brenner = {p["id"]: p["decision"] for p in hcp360.view("hcp-brenner")["planned"]}
    assert any("consent" in r for r in brenner["plan-brenner-email"]["reasons"])
    assert any("inq-103" in r for r in brenner["plan-brenner-visit"]["reasons"])


def test_field_rep_sees_status_but_not_case_detail():
    run("inq-103")
    c = TestClient(api.app)
    assert "redacted" in c.get("/api/cases/inq-103", headers={"X-User": "u-becker"}).json()
    assert c.get("/api/cases/inq-103", headers={"X-User": "u-brandt"}).json()["draft"]


def test_api_refuses_approval_with_403_and_reason():
    run("inq-103")
    r = TestClient(api.app).post("/api/cases/inq-103/approve", headers={"X-User": "u-hale"})
    assert r.status_code == 403 and "Verified Permissions" in r.json()["detail"]
