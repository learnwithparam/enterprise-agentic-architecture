"""Fail on em or en dashes and filler words in docs, labs and UI copy. Wired into make check."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [*ROOT.glob("*.md"), *ROOT.glob("docs/**/*.md"), *ROOT.glob("labs/**/*.md"), *ROOT.glob(".claude/**/*.md"), *ROOT.glob("web/src/**/*.astro"),
         *ROOT.glob("web/src/**/*.ts"), *ROOT.glob("world/*.toml")]
BANNED = re.compile(r"[—–]|\b(delve|seamless(ly)?|leverag(e|ing)|robust|cutting-edge|game-?changer|unlock(s|ing)?|empower(s|ing)?)\b", re.I)


def main() -> int:
    bad = 0
    for f in FILES:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            for m in BANNED.finditer(line):
                print(f"{f.relative_to(ROOT)}:{n}: '{m.group(0)}'")
                bad += 1
    print(f"prose: {bad} problems in {len(FILES)} files")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
