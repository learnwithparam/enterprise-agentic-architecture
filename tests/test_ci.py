"""The security checks are wired into CI, not only described (Rule 0, ADR 0029)."""

from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml").read_text()


def test_ci_runs_the_gate_and_every_security_check_on_each_pull_request():
    assert "pull_request:" in WORKFLOW
    for step in ("run: make check", "zricethezav/gitleaks", "uvx pip-audit", "cyclonedx-py environment", "codeql-action/analyze"):
        assert step in WORKFLOW, f"CI does not run {step}"


def test_ci_scans_on_a_schedule_so_new_advisories_surface_without_a_push():
    assert "schedule:" in WORKFLOW and "cron:" in WORKFLOW


def test_every_ci_dependency_is_pinned():
    for line in WORKFLOW.splitlines():
        if "uses:" in line:
            assert "@" in line and not line.strip().endswith("@main"), line
        if "uvx" in line:
            assert "==" in line, line
