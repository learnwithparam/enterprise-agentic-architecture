"""Fail when a doc reads harder than it did. Wired into make check.

Every doc and lab README is scored by the same grade formula as the code gate. The goal is grade 6.5.
A doc above the goal is listed in docs_grade_baseline.json with its current grade. It may get easier. It may not get harder.
When a doc reaches the goal its entry is removed, and from then on it must stay at the goal.
Run with --update to lower the baseline after you make docs easier.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "docs_grade_baseline.json"
SKIPPED_STARTS = ("|", "#", "!", "-", "*", "<", "    ", ">")

spec = importlib.util.spec_from_file_location("check_readable", ROOT / "scripts" / "check_readable.py")
readable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readable)


def prose_of(text: str) -> str:
    """The sentences of a doc. Code blocks, tables, headings, lists and quotes are left out."""
    kept = []
    inside_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            inside_code = not inside_code
            continue
        if inside_code or not stripped or line.lstrip().startswith(SKIPPED_STARTS) or stripped[0].isdigit():
            continue
        kept.append(stripped)
    return " ".join(kept)


def doc_files() -> list[Path]:
    found = sorted((ROOT / "docs").rglob("*.md")) + sorted((ROOT / "labs").glob("*/README.md"))
    return found + [ROOT / "README.md"]


def grades() -> dict[str, float]:
    scores = {}
    for path in doc_files():
        text = prose_of(path.read_text())
        if text:
            scores[str(path.relative_to(ROOT))] = round(readable.grade_of(text), 1)
    return scores


def problems(scores: dict[str, float], baseline: dict[str, float]) -> list[str]:
    found = []
    for name, grade in scores.items():
        allowed = max(readable.HIGHEST_GRADE, baseline.get(name, 0))
        if grade > allowed:
            found.append(f"{name}: reads at grade {grade}; keep it at {allowed} or lower")
    return found


def main() -> int:
    scores = grades()
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    if "--update" in sys.argv:
        harder = {name: grade for name, grade in scores.items() if grade > readable.HIGHEST_GRADE}
        kept = {name: min(grade, baseline.get(name, grade)) for name, grade in harder.items()}
        BASELINE.write_text(json.dumps(dict(sorted(kept.items())), indent=1) + "\n")
        print(f"docs: baseline holds {len(kept)} docs above grade {readable.HIGHEST_GRADE}")
        return 0
    found = problems(scores, baseline)
    for line in found:
        print(line)
    print(f"docs: {len(found)} problems, {len(baseline)} docs still above grade {readable.HIGHEST_GRADE} in the baseline")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
