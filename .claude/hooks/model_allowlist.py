"""PreToolUse hook: refuse an edit that puts a Claude model id outside the allowlist into code or config.

Two models are allowed, claude-haiku-5-5 and claude-sonnet-5-5, because the model router picks between
them. The eval gate passed on exactly those two. A third id in src/, web/, world/, evals/, policies/ or
scripts/ would ship a model the gate never saw. tests/, labs/ and docs/ may name other models as examples
of what is refused. Exit 2 blocks the edit and shows the reason to Claude.
"""

import json
import re
import sys

ALLOWED = frozenset({"claude-haiku-5-5", "claude-sonnet-5-5"})
GUARDED = ("src/", "web/app/", "web/components/", "web/lib/", "web/scripts/", "world/", "evals/", "policies/", "scripts/", "prompts/")
MODEL_ID = re.compile(r"\bclaude-[a-z0-9.-]*(?:opus|sonnet|haiku|fable)[a-z0-9.-]*", re.I)


def offending(text: str) -> list[str]:
    return sorted({m.group(0).rstrip(".-") for m in MODEL_ID.finditer(text)} - ALLOWED)


def relative(path: str, root: str) -> str:
    return path[len(root):].lstrip("/") if root and path.startswith(root) else path


def main() -> int:
    event = json.load(sys.stdin)
    inp = event.get("tool_input", {})
    path = relative(inp.get("file_path", ""), event.get("cwd", ""))
    if not path.startswith(GUARDED):
        return 0
    text = "\n".join([inp.get("content", ""), inp.get("new_string", ""),
                      *(e.get("new_string", "") for e in inp.get("edits", []))])
    bad = offending(text)
    if not bad:
        return 0
    print(f"{path}: only {', '.join(sorted(ALLOWED))} may appear in code and config; found {', '.join(bad)}. "
          "A model change is a release: see .claude/skills/record-prompt-version.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
