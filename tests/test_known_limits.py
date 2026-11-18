"""The case study and the Floci page list the same limits, and the Floci table lists SES."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


def bullets(path: str, heading: str) -> set[str]:
    """The first six words, lowercased, of each bullet under the heading."""
    text = (DOCS / path).read_text()
    start = text.index(heading)
    found = set()
    for line in text[start:].splitlines()[1:]:
        if line.startswith("- "):
            found.add(" ".join(line[2:].lower().split()[:6]))
        elif found and not line.strip():
            break
    return found


def test_both_pages_list_the_same_limits():
    case = bullets("case-study.md", "**Known limits of this build.**")
    floci = bullets("floci-support.md", "## Limits that remain")
    assert case and floci
    assert case == floci


def test_the_floci_table_lists_ses():
    services = re.findall(r"^\| ([^|]+) \|", (DOCS / "floci-support.md").read_text(), re.MULTILINE)
    assert "SES" in [name.strip() for name in services]
