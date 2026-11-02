"""The guardian only tightens, the improver only proposes, and the red-team corpus never gets through (ADR 0026)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, cases, evals, guardian, improver, infra, ledger, redteam, rules, store, world

from tests.test_flow import as_user

pytestmark = pytest.mark.floci


def review(country: str, approved: int, rejected: int, topic: str = "dosing") -> list[str]:
    """Seed reviewed AI drafts the way approve and reject leave them: a case with a draft, and a ledger entry."""
    ids = []
    for kind, n in (("approved", approved), ("rejected", rejected)):
        for i in range(n):
            cid = f"t-{country}-{kind}-{i}-{datetime.now(UTC).timestamp()}"
            store.put("mi-cases", {"id": cid, "country": country, "product": "p", "draft": {"segments": []},
                                   "questions": [{"topic": topic}]})
            ledger.append({"case": cid, "type": kind})
            ids.append(cid)
    return ids


def test_reviewers_who_reject_too_much_switch_a_country_off_and_a_human_switches_it_back():
    infra.provision(reset=True)
    start = datetime.now(UTC)
    review("DE", approved=2, rejected=4)
    assert cases.autonomy_setting("DE")["enabled"]
    lowered = guardian.patrol(start)
    assert [c["country"] for c in lowered] == ["DE"]
    assert not cases.autonomy_setting("DE")["enabled"]
    assert guardian.patrol(start) == []  # nothing left to lower
    assert cases.autonomy_setting("US")["enabled"]
    assert any(r["entry"]["type"] == "guardian_lowered" for r in ledger.entries())
    # a human switches it back on: the old rejections no longer count
    cases.save_autonomy("DE", cases.autonomy_setting("DE") | {"enabled": True})
    ledger.append({"type": "autonomy_changed", "country": "DE", "enabled": True, "user": "u-test"})
    assert guardian.patrol(start) == [] and cases.autonomy_setting("DE")["enabled"]


def test_a_few_decisions_or_a_low_override_rate_change_nothing():
    infra.provision(reset=True)
    start = datetime.now(UTC)
    review("US", approved=0, rejected=3)  # too few to judge
    review("DE", approved=9, rejected=1)  # well inside the limit
    assert guardian.patrol(start) == []
    assert cases.autonomy_setting("US")["enabled"] and cases.autonomy_setting("DE")["enabled"]


def test_the_guardian_never_raises_autonomy():
    infra.provision(reset=True)
    start = datetime.now(UTC)
    cases.save_autonomy("DE", cases.autonomy_setting("DE") | {"enabled": False})
    review("DE", approved=9, rejected=0)  # a spotless record
    assert guardian.patrol(start) == []
    assert not cases.autonomy_setting("DE")["enabled"]


def test_a_topic_reviewers_keep_rejecting_becomes_one_proposal_and_nothing_is_promoted():
    infra.provision(reset=True)
    review("DE", approved=0, rejected=2, topic="storage")
    mine = lambda: [p for p in improver.propose() if p["country"] == "DE" and p["topic"] == "storage"]  # noqa: E731
    review("DE", approved=0, rejected=1, topic="administration")  # one correction is not a pattern
    assert not [p for p in improver.propose() if p["topic"] == "administration"]
    first = mine()
    assert len(first) == 1 and first[0]["status"] == "proposed" and len(first[0]["cases"]) == 2
    assert mine() == first  # asking again adds nothing
    assert cases.autonomy_setting("DE")["topics"] == world.autonomy_seed()["auto_send"]["DE"]  # the policy is untouched


def test_every_attack_in_the_corpus_is_caught():
    assert len(redteam.attacks()) >= 8
    assert redteam.misses() == []
    assert not rules.injection_screen("What is the usual starting dose for adults?")


def test_a_redteam_miss_fails_the_eval_gate():
    ok = {"route_acceptable": 1.0, "ae_recall": 1.0, "ungrounded_sentences": 0, "unsafe_auto_sends": 0,
          "off_allowlist_calls": 0, "redteam_misses": 0, "max_cost_per_case_usd": 0.001}
    assert evals.gate(ok) == []
    assert any("redteam_misses" in f for f in evals.gate({**ok, "redteam_misses": 1}))


def test_listing_proposals_writes_nothing_and_refreshing_does():
    infra.provision(reset=True)
    review("DE", approved=0, rejected=2, topic="storage")
    c = TestClient(api.app)
    h = as_user("u-becker")
    assert c.get("/api/proposals", headers=h).json() == []
    assert c.get("/api/proposals").status_code == 401
    assert c.post("/api/proposals/refresh", headers=h).status_code == 403
    assert [p["topic"] for p in c.post("/api/proposals/refresh", headers=as_user("u-brandt")).json()] == ["storage"]
    assert [p["topic"] for p in c.get("/api/proposals", headers=h).json()] == ["storage"]
