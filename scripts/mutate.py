"""Break each safety property one at a time and require a check to fail. Wired into make check.

A mutant that survives means the property has no test that bites; the run fails until one is written.
Each mutant names the narrowest check that should catch it, so the run takes seconds, not minutes.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTEST = ["uv", "run", "pytest", "-q", "-x", "-p", "no:cacheprovider"]

# (property, file, original text, mutated text, check that must fail)
MUTANTS = [
    ("An adverse event always goes to pharmacovigilance", "src/hcpagents/graph.py",
     '    ("ae", True, "pv",', '    ("ae_off", True, "pv",', [*PYTEST, "tests/test_graph.py"]),
    ("An injection attempt is declined", "src/hcpagents/graph.py",
     '    ("injection", True, "decline",', '    ("injection", "never", "decline",', [*PYTEST, "tests/test_graph.py"]),
    ("Only current blocks count as evidence", "src/hcpagents/grounding.py",
     "live = [b for b in sources if is_current(b, today)]", "live = sources", [*PYTEST, "tests/test_grounding.py"]),
    ("The send rechecks content and fails closed", "src/hcpagents/cases.py",
     '    if not check["grounded"]:\n        d["status"] = "blocked_at_send"', '    if False:\n        d["status"] = "blocked_at_send"',
     [*PYTEST, "tests/test_flow.py::test_withdrawn_content_invalidates_the_draft_and_blocks_the_send"]),
    ("A tool call stays in the case's country and product", "src/hcpagents/guards.py",
     'if country != case["country"] or product != case["product"]:', "if False:",
     [*PYTEST, "tests/test_rules.py::test_tool_guard_blocks_other_countries_and_unknown_tools"]),
    ("Only Haiku 5.5 may answer", "src/hcpagents/agents.py",
     "    others = sorted(set(model_usage or {}) - {MODEL})", "    others = []", [*PYTEST, "tests/test_model_policy.py"]),
    ("A reviewer approves only in their own country", "policies/cedar/reviewers.cedar",
     ' &&\n  resource.country == principal.country', "",
     [*PYTEST, "tests/test_flow.py::test_reviewer_approves_only_in_their_own_country"]),
    ("Nobody approves on a pharmacovigilance case", "policies/cedar/reviewers.cedar",
     'when { resource.route == "pv" };', 'when { resource.route == "never" };',
     [*PYTEST, "tests/test_flow.py::test_nobody_approves_on_a_pharmacovigilance_case"]),
    ("A field rep reads only the inquiries they submitted", "policies/cedar/cases.cedar",
     'principal.role != "field_rep" || resource.submitter == principal.name', 'principal.role != "field_rep" || resource.submitter != ""',
     [*PYTEST, "tests/test_flow.py::test_field_rep_reads_only_the_inquiries_they_submitted"]),
    ("A missing user never falls back to anyone", "src/hcpagents/api.py",
     '    if not x_user:\n        raise HTTPException(401, "Name the acting user in the X-User header")\n',
     '    x_user = x_user or "u-raman"\n',
     [*PYTEST, "tests/test_flow.py::test_every_api_route_refuses_a_caller_cognito_does_not_know"]),
    ("Every API route needs a known user", "src/hcpagents/api.py",
     'if request.url.path.startswith("/api/"):', 'if request.url.path.startswith("/none/"):',
     [*PYTEST, "tests/test_flow.py::test_every_api_route_refuses_a_caller_cognito_does_not_know"]),
]


def main() -> int:
    survived = 0
    for prop, rel, old, new, check in MUTANTS:
        p = ROOT / rel
        orig = p.read_text()
        if orig.count(old) != 1:
            print(f"mutate: the text for '{prop}' is no longer in {rel}; update scripts/mutate.py")
            return 1
        p.write_text(orig.replace(old, new))
        try:
            r = subprocess.run(check, cwd=ROOT, capture_output=True, text=True)
        finally:
            p.write_text(orig)
        caught = r.returncode != 0
        survived += not caught
        print(f"{'killed  ' if caught else 'SURVIVED'} {prop} ({rel})")
    print(f"mutate: {len(MUTANTS) - survived} of {len(MUTANTS)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
