"""The coordinator holds what policy forbids and the supervisor settles overlaps; neither ever sends (ADR 0023)."""

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, infra, ledger, outreach, store, supervisor, world
from tests.test_flow import as_user, run

pytestmark = pytest.mark.floci


def by_id(decisions):
    return {d["id"]: d for d in decisions}


def test_an_open_medical_case_holds_the_promotion_and_the_reason_points_at_the_case():
    infra.provision(reset=True)
    run("inq-103")
    visit = by_id(outreach.coordinate("hcp-brenner"))["plan-brenner-visit"]
    assert visit["action"] == "hold"
    assert {"rule": "open_medical_case", "source": "inq-103"} == {k: visit["reasons"][0][k] for k in ("rule", "source")}


def test_no_consent_holds_the_email_and_every_decision_is_a_proposal_or_a_hold():
    infra.provision(reset=True)
    run("inq-103")
    email = by_id(outreach.coordinate("hcp-brenner"))["plan-brenner-email"]
    assert email["action"] == "hold" and "consent" in [r["rule"] for r in email["reasons"]]
    assert {d["action"] for h in ("hcp-kaya", "hcp-brenner", "hcp-okafor") for d in outreach.coordinate(h)} <= {"propose", "hold"}


def test_two_proposals_within_days_of_each_other_yield_to_the_one_that_serves_the_doctor():
    a = {"id": "promo", "on": "2026-10-20", "promotional": True}
    b = {"id": "reply", "on": "2026-10-22", "promotional": False}
    far = {"id": "later", "on": "2026-11-20", "promotional": True}
    assert supervisor.arbitrate([a, b, far]) == {"promo": "reply"}
    assert supervisor.arbitrate([{"id": "x", "on": "2026-10-20"}, {"id": "y", "on": "2026-10-21"}]) == {"y": "x"}


def test_a_clear_touch_is_proposed_a_later_overlap_is_held_and_each_hold_is_ledgered():
    infra.provision(reset=True)
    base = {"hcp": "hcp-okafor", "product": "VEL", "promotional": False, "kind": "email", "channel": "marketing",
            "status": "planned", "summary": "Test touch."}
    with world.as_tenant("quillon"):
        store.put("mi-touches", base | {"id": "t-first", "on": "2026-11-02"})
        store.put("mi-touches", base | {"id": "t-second", "on": "2026-11-03"})
        got = by_id(outreach.run("hcp-okafor"))
        assert got["t-first"]["action"] == "propose" and got["t-second"]["action"] == "hold"
        assert got["t-second"]["reasons"][0] == {"rule": "overlap", "why": got["t-second"]["reasons"][0]["why"], "source": "t-first"}
        assert store.get("mi-touches", "t-second")["coordinator"] == "hold"
        held = [r["entry"] for r in ledger.entries() if r["entry"].get("touch") == "t-second"]
        assert [(e["type"], e["rules"]) for e in held] == [("outreach_hold", ["overlap"])]
        outreach.run("hcp-okafor")  # an unchanged decision is not ledgered twice
        assert len([r for r in ledger.entries() if r["entry"].get("touch") == "t-second"]) == 1


def test_the_outreach_plan_is_served_per_tenant():
    infra.provision(reset=True)
    c = TestClient(api.app)
    assert c.get("/api/hcps/hcp-kaya/outreach", headers=as_user("u-becker")).status_code == 200
    assert c.get("/api/hcps/hcp-m-ortiz/outreach", headers=as_user("u-becker")).status_code == 404
