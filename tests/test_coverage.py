"""The coverage table and the validation pack name only things that exist, and every required topic has a row."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

REQUIRED_TOPICS = [
    "Overlapping messages", "Pharmacovigilance", "Off-label", "injection", "Audit trail", "erasure", "signature",
    "Solution shaping", "Governance gates", "vendor-agnostic", "embeddings", "mutation testing", "DevSecOps",
    "Data engineering", "AWS", "Docker", "LLMOps", "EU AI Act", "Regulated industry",
    "Planning", "Graph engineering", "policy kernel", "Model routing", "MCP", "arbitration", "Shared memory",
    "Perception", "Autonomy levels", "Verification", "Guardrails", "Authentication", "Authorization",
    "Multi-tenant", "Caching", "Long running", "Always on", "Idempotency", "Self-improvement", "Red-team",
    "Cost control", "Harness engineering", "Observability", "CLI", "Endpoints", "SaaS console",
]


def _rows(path: Path) -> list[list[str]]:
    rows = []
    for line in path.read_text().splitlines():
        if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def _coverage_rows() -> list[list[str]]:
    return [r for r in _rows(DOCS / "coverage.md") if len(r) == 5 and r[0] != "Requirement"]


def _test_exists(ref: str) -> bool:
    file, _, name = ref.partition("::")
    path = ROOT / file
    return path.is_file() and re.search(rf"^(async )?def {re.escape(name)}\(", path.read_text(), re.M) is not None


def _mutant_names() -> set[str]:
    return set(re.findall(r'^    \("([^"]+)", "', (ROOT / "scripts" / "mutate.py").read_text(), re.M))


def test_every_coverage_row_names_a_doc_screen_lab_and_test_that_exist():
    nav = (ROOT / "web" / "components" / "Shell.jsx").read_text()
    problems = []
    for req, doc, screen, lab, test in _coverage_rows():
        if not (DOCS / doc).is_file():
            problems.append(f"{req}: no doc {doc}")
        if screen != "-" and f"'{screen}'" not in nav:
            problems.append(f"{req}: no screen {screen}")
        if lab != "-" and not (ROOT / "labs" / lab).is_dir():
            problems.append(f"{req}: no lab {lab}")
        if not _test_exists(test):
            problems.append(f"{req}: no test {test}")
    assert not problems, "\n".join(problems)


def test_every_required_topic_has_a_row():
    text = "\n".join(r[0] for r in _coverage_rows()).lower()
    missing = [t for t in REQUIRED_TOPICS if t.lower() not in text]
    assert not missing, f"no coverage row for: {missing}"


def test_the_validation_pack_names_tests_and_mutants_that_exist():
    mutants = _mutant_names()
    problems = []
    for row in _rows(DOCS / "validation-pack.md"):
        if len(row) != 3 or row[0] == "Requirement":
            continue
        req, test, mutant = row
        ref = test.strip("`")
        if not _test_exists(ref):
            problems.append(f"{req}: no test {ref}")
        if mutant not in mutants:
            problems.append(f"{req}: no mutant {mutant!r}")
    assert not problems, "\n".join(problems)
