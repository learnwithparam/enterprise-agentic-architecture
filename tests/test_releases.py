"""A release is a hash of what decides behaviour, and a worse release than the baseline is blocked (ADR 0025)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from hcpagents import agents, api, db, evals, infra, releases, world
from tests.test_flow import as_user

pytestmark = pytest.mark.floci

GOOD = {"route_acceptable": 1.0, "ae_recall": 1.0, "max_cost_per_case_usd": 0.002,
        "avg_cost_per_case_usd": 0.001, "sonnet_case_rate": 0.1}


@pytest.fixture(autouse=True)
def migrated():
    db.migrate()


def rid() -> str:
    return "r-t" + uuid.uuid4().hex[:6]


def test_the_release_id_follows_the_prompt(monkeypatch):
    before = releases.release_id()
    assert before == releases.release_id()
    spec = agents.AGENTS["triage"]
    monkeypatch.setitem(agents.AGENTS, "triage", {**spec, "system": spec["system"] + " Be brief."})
    assert releases.release_id() != before
    assert releases.manifest()["prompts"]["safety"] == releases.manifest()["prompts"]["safety"]


def test_a_metric_worse_than_the_baseline_is_a_regression():
    assert releases.regressions(GOOD, GOOD) == []
    assert releases.regressions({**GOOD, "route_acceptable": 0.9}, GOOD)
    assert releases.regressions({**GOOD, "ae_recall": 0.95}, GOOD)
    assert releases.regressions({**GOOD, "avg_cost_per_case_usd": 0.002}, GOOD)
    assert releases.regressions({**GOOD, "sonnet_case_rate": 0.5}, GOOD)
    assert releases.regressions({**GOOD, "avg_cost_per_case_usd": 0.0005, "route_acceptable": 1.0}, GOOD) == []


def test_only_a_clean_run_can_become_the_baseline():
    with world.as_tenant("marlowe"):
        bad, good = rid(), rid()
        releases.record(bad, releases.manifest(), GOOD, False, ["ae_recall fell"])
        with pytest.raises(ValueError):
            releases.promote(bad)
        releases.record(good, releases.manifest(), GOOD, True, [])
        releases.promote(good)
        assert releases.baseline()["release"] == good
        with pytest.raises(LookupError):
            releases.promote("r-missing")


def test_the_eval_gate_blocks_a_release_that_regresses(monkeypatch, tmp_path):
    infra.provision(reset=True)
    with world.as_tenant("marlowe"):
        base = rid()
        releases.record(base, releases.manifest(), GOOD, True, [])
        releases.promote(base)
        rows = [{"id": "x", "expect": "review", "also_safe": [], "route": "review", "acceptable": True, "ungrounded": 0,
                 "cost_usd": 0.0001, "models": [agents.SONNET], "why": "", "decision": {}}]
        async def fake(): return rows
        monkeypatch.setattr(evals, "run_all", fake)
        monkeypatch.setattr(evals, "REPORT", tmp_path / "report.json")
        monkeypatch.setattr(evals, "score", lambda r: {**GOOD, "ungrounded_sentences": 0, "unsafe_auto_sends": 0,
                                                       "off_allowlist_calls": 0, "redteam_misses": 0, "sonnet_case_rate": 0.9, "cases": 1})
        assert evals.main() == 1
        assert "sonnet_case_rate" in " ".join(__import__("json").loads((tmp_path / "report.json").read_text())["failures"])


def test_a_diff_names_the_metrics_and_the_parts_that_changed():
    with world.as_tenant("marlowe"):
        a, b = rid(), rid()
        m = releases.manifest()
        releases.record(a, m, GOOD, True, [])
        releases.record(b, {**m, "kernel": "other"}, {**GOOD, "avg_cost_per_case_usd": 0.0012}, True, [])
        d = releases.diff(a, b)
        assert d["changed"] == ["kernel"]
        assert d["metrics"]["avg_cost_per_case_usd"]["delta"] == pytest.approx(0.0002)


def test_the_releases_route_lists_runs_and_a_tenant_sees_only_its_own():
    with world.as_tenant("marlowe"):
        mine = rid()
        releases.record(mine, releases.manifest(), GOOD, True, [])
    infra.provision(reset=True)
    assert mine not in [r["release"] for r in releases.trend("quillon")]
    assert mine in [r["release"] for r in releases.trend("marlowe")]
    assert TestClient(api.app).get("/api/releases").status_code == 401
    r = TestClient(api.app).get("/api/releases", headers=as_user("u-becker"))
    assert r.status_code == 200 and mine not in [x["release"] for x in r.json()]
