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


_PATH_ROOTS = ("docs/", "src/", "tests/", "labs/", "scripts/", "policies/", "evals/", "migrations/", "deploy/", "world/")
_PATH_EXT = (".py", ".md", ".toml", ".sql", ".cedar", ".json", ".yaml", ".yml")


def _prose_files() -> list[Path]:
    return [ROOT / "README.md", *sorted(DOCS.glob("*.md")), *sorted(DOCS.glob("adr/*.md")), *sorted(ROOT.glob("labs/*/README.md"))]


def test_md_links_resolve():
    """Every relative link and every backticked repo path in the docs and lab READMEs names a file that exists."""
    problems = []
    for md in _prose_files():
        text = md.read_text()
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not (md.parent / target.split("#")[0]).exists():
                problems.append(f"{md.relative_to(ROOT)}: link {target}")
        for ref in re.findall(r"`([^`\s]+)`", text):
            file, _, name = ref.partition("::")
            if not file.startswith(_PATH_ROOTS) or not file.endswith(_PATH_EXT) or any(c in file for c in "*<>{}"):
                continue
            if name and file.startswith("tests/"):
                ok = _test_exists(ref)
            else:
                ok = (ROOT / file).exists()
            if not ok:
                problems.append(f"{md.relative_to(ROOT)}: path {ref}")
    assert not problems, "\n".join(sorted(set(problems)))


def _labs() -> list[Path]:
    return sorted(p for p in (ROOT / "labs").iterdir() if p.is_dir() and (p / "README.md").is_file())


def test_every_lab_is_in_session_map():
    """Both the top README and the labs index link every lab folder, so a lab nobody can find does not ship."""
    problems = []
    for index in (ROOT / "README.md", ROOT / "labs" / "README.md"):
        text = index.read_text()
        for lab in _labs():
            if f"labs/{lab.name}/" not in text and f"({lab.name}/)" not in text:
                problems.append(f"{index.relative_to(ROOT)} does not link {lab.name}")
    assert len(_labs()) >= 14 and not problems, "\n".join(problems)


def test_every_lab_with_a_test_named_in_coverage_has_its_row_filled():
    """A dash in the Lab column is only allowed where no lab teaches the row's test file."""
    taught = {"test_durable.py": "keep-a-case-alive-with-temporal", "test_tenancy.py": "isolate-tenants-with-row-level-security",
              "test_retrieval.py": "retrieve-behind-a-facet-gate", "test_guardian.py": "let-the-guardian-only-tighten"}
    problems = [f"{req}: Lab is - but {lab} teaches {Path(test).name}" for req, _, _, l, test in _coverage_rows()
                for name, lab in taught.items() if l == "-" and Path(test.partition("::")[0]).name == name]
    assert not problems, "\n".join(problems)


def test_lab_readme_shape():
    """Every lab README has prerequisites, a diagram of how it works, and at least one line the learner can check."""
    problems = []
    for lab in _labs():
        text = (lab / "README.md").read_text()
        if not re.search(r"^## Prerequisites$", text, re.M):
            problems.append(f"{lab.name}: no Prerequisites section")
        if "```mermaid" not in text:
            problems.append(f"{lab.name}: no mermaid diagram")
        if not re.search(r"^Expect: ", text, re.M):
            problems.append(f"{lab.name}: no Expect: line")
        if not re.search(r"^## Break it", text, re.M):
            problems.append(f"{lab.name}: no Break it section")
    assert not problems, "\n".join(problems)
