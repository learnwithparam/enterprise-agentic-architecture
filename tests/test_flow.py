"""End to end on Floci, in replay: the moments a human stays in control, and the proof Compliance checks."""

import asyncio

import jwt
import pytest
from fastapi.testclient import TestClient

from hcpagents import api, auth, cases, hcp360, infra, ledger, store, v1, world

pytestmark = pytest.mark.floci

BRANDT, HALE, WEBER, BECKER, RAMAN, LIND = (world.person(u) for u in ("u-brandt", "u-hale", "u-weber", "u-becker", "u-raman", "u-lind"))


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def as_user(user_id):
    """Sign in through the API, as the console does, and return the Authorization header."""
    r = TestClient(api.app).post("/api/login", json={"user": user_id, "password": auth.DEMO_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def run(i):
    return asyncio.run(cases.run(i))


def sign(user):
    """The approver's fresh sign-in, as the console sends it."""
    return auth.reauthenticate(user, auth.DEMO_PASSWORD)


def test_auto_send_records_a_touch_on_the_hcp_timeline():
    d = run("inq-101")
    assert d["status"] == "sent" and d["send_check"]["grounded"]
    assert any(t.get("case") == "inq-101" for t in hcp360.timeline("hcp-kaya"))


def test_reviewer_approves_only_in_their_own_country():
    run("inq-103")
    with pytest.raises(cases.Denied):
        cases.approve("inq-103", HALE, sign(HALE))
    assert cases.approve("inq-103", BRANDT, sign(BRANDT))["status"] == "sent"


def test_nobody_approves_on_a_pharmacovigilance_case():
    d = run("inq-105")
    assert d["draft"] is None and d["status"] == "with_pharmacovigilance"
    # Hale reviews in the US, the case's country, so only the pharmacovigilance forbid can refuse him here.
    with pytest.raises(cases.Denied, match="may not ApproveReply on inq-105. Verified Permissions: DENY"):
        cases.approve("inq-105", HALE, sign(HALE))


def test_withdrawn_content_invalidates_the_draft_and_blocks_the_send():
    run("inq-103")
    with pytest.raises(cases.Denied):
        cases.withdraw("VEL-DE-RENAL", BECKER, "not my job")
    assert cases.withdraw("VEL-DE-RENAL", WEBER, "Label update")["queued"]
    assert cases.process_invalidations()["cases"] == ["inq-103"]  # what the steward does on its next pass
    d = cases.approve("inq-103", BRANDT, sign(BRANDT))
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
    assert "redacted" in c.get("/api/cases/inq-103", headers=as_user("u-becker")).json()
    assert c.get("/api/cases/inq-103", headers=as_user("u-brandt")).json()["draft"]


def test_api_refuses_approval_with_403_and_reason():
    with TestClient(api.app) as c:  # the lifespan runs the worker
        c.post("/api/inquiries/inq-103/run", headers=as_user("u-brandt"))
        r = c.post("/api/cases/inq-103/approve", headers=as_user("u-hale"), json={"password": auth.DEMO_PASSWORD})
    assert r.status_code == 403 and "Verified Permissions" in r.json()["detail"]


def test_every_api_and_v1_route_refuses_a_caller_without_a_verified_token():
    c = TestClient(api.app)
    # FastAPI wraps an included router in one entry without a path, so /v1 is read from its own router.
    routes = [(m, r.path) for r in [*api.app.routes, *v1.router.routes]
              if getattr(r, "path", "").startswith(("/api/", "/v1/")) and r.path not in api.PUBLIC for m in r.methods]
    assert any(path.startswith("/v1/") for _, path in routes)
    assert len(routes) > 20
    forged = {"Authorization": "Bearer " + jwt.encode({"sub": "x", "cognito:username": "u-raman"}, "k" * 32, algorithm="HS256")}
    for method, route in routes:
        url = route.replace("{", "").replace("}", "")
        for headers in ({}, {"X-User": "u-raman"}, {"Authorization": "Bearer nonsense"}, forged):
            r = c.request(method, url, headers=headers, json={})
            assert r.status_code == 401, (method, route, headers, r.status_code)


def test_login_refuses_a_wrong_password_and_a_signed_token_opens_the_session():
    c = TestClient(api.app)
    assert c.post("/api/login", json={"user": "u-raman", "password": "wrong"}).status_code == 401
    s = c.get("/api/session", headers=as_user("u-raman")).json()["user"]
    assert s["id"] == "u-raman" and s["tenant"] == "quillon"


def test_a_token_for_another_audience_is_refused(monkeypatch):
    headers = as_user("u-raman")
    monkeypatch.setattr(auth, "client_id", lambda: "some-other-app")
    assert TestClient(api.app).get("/api/session", headers=headers).status_code == 401


def test_field_rep_reads_only_the_inquiries_they_submitted():
    rows = {i["id"]: i for i in TestClient(api.app).get("/api/inquiries", headers=as_user("u-becker")).json()}
    assert rows["inq-102"]["text"]
    assert rows["inq-111"]["text"] is None
    assert rows["inq-103"]["text"] is None


def test_only_compliance_resets_the_platform():
    r = TestClient(api.app).post("/api/reset", headers=as_user("u-becker"))
    assert r.status_code == 403 and "Verified Permissions" in r.json()["detail"]


def test_a_second_client_sees_only_its_own_world():
    run("inq-101")
    c, reyes = TestClient(api.app), as_user("u-reyes")
    assert c.get("/api/cases", headers=reyes).json() == []
    assert c.get("/api/cases/inq-101", headers=reyes).status_code == 404
    meta = c.get("/api/meta", headers=reyes).json()
    assert meta["company"] == "Marlowe Therapeutics" and [p["id"] for p in meta["people"]] == ["u-reyes"]
    assert {b["id"] for b in c.get("/api/content", headers=reyes).json()} == {"TPL-OPEN", "TPL-CLOSE", "TPL-AI-US", "CAR-US-DOSE"}
    assert [i["id"] for i in c.get("/api/inquiries", headers=reyes).json()] == ["inq-m-201"]


def test_the_first_client_never_sees_the_second():
    c, raman = TestClient(api.app), as_user("u-raman")
    assert "u-reyes" not in [p["id"] for p in c.get("/api/meta", headers=raman).json()["people"]]
    assert c.get("/api/hcps/hcp-m-ortiz", headers=raman).status_code == 404


def test_cedar_refuses_a_principal_acting_across_tenants():
    from hcpagents import authz
    with world.as_tenant("marlowe"):
        ok, why = authz.user_can(BRANDT | {"tenant": "quillon"}, "ViewCaseDetail", "Case", "x", {"country": "DE", "route": "send"})
        assert not ok and "tenants.cedar" in why
        ok, _ = authz.user_can(world.person("u-reyes"), "ViewCaseDetail", "Case", "x", {"country": "US", "route": "send"})
        assert ok


def test_sign_in_options_list_people_of_every_tenant_and_no_credential():
    with TestClient(api.app) as c:
        r = c.get("/api/login-options")
    assert r.status_code == 200
    body = r.json()
    assert {t["id"] for t in body["tenants"]} >= {"quillon", "marlowe"}
    assert {"u-brandt", "u-reyes"} <= {p["id"] for p in body["people"]}
    assert all(set(p) == {"id", "name", "role", "country", "title", "tenant"} for p in body["people"])


def test_agents_endpoint_lists_the_roster_with_a_goal_and_a_limit_for_each():
    with TestClient(api.app) as c:
        r = c.get("/api/agents", headers=as_user("u-raman"))
    assert r.status_code == 200
    roster = r.json()["agents"]
    assert {"supervisor", "sentinel", "inquiry", "outreach", "steward", "insight", "guardian", "improver"} == {a["id"] for a in roster}
    assert all(a["goal"] and a["never"] and a["acts_alone"] for a in roster)
