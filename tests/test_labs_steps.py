"""Each lab README lists the `# Step` comments of one real function, and the list must match the code.

Each lab README also has the learner shape: goals, one diagram, the console shot that labs/README.md names
(or terminal output), folded self-check answers, and learner issues to try next."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENTENCE = re.compile(r"These are the `# Step` comments in `(\w+)`\.")
STEP = re.compile(r"\s*# Step \d+: (.*)")
EXCEPTIONS = 0
MINIMUM = 20 - EXCEPTIONS


def code_steps(name: str) -> list[list[str]]:
    """The step comments of every function with this name, one list per function."""
    found = []
    for path in sorted((ROOT / "src" / "hcpagents").glob("*.py")):
        source = path.read_text()
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                matches = [STEP.match(line) for line in lines[node.lineno - 1 : node.end_lineno]]
                found.append([match.group(1) for match in matches if match])
    return found


def test_each_lab_steps_match_the_code():
    labs_with_steps = 0
    for readme in sorted((ROOT / "labs").glob("*/README.md")):
        text = readme.read_text()
        sentence = SENTENCE.search(text)
        if sentence is None:
            continue
        labs_with_steps += 1
        listed = text.split("## Steps")[1].split(sentence.group(0))[0]
        listed_steps = re.findall(r"(?m)^\d+\. (.*)$", listed)
        assert listed_steps, f"{readme.parent.name}: no numbered list"
        assert listed_steps in code_steps(sentence.group(1)), f"{readme.parent.name}: steps differ from the code"
    assert labs_with_steps >= MINIMUM


LEARNER_SECTIONS = ["## What you will learn", "## How it works", "## Check yourself", "## Try next"]
ISSUES = "https://github.com/learnwithparam/enterprise-agentic-architecture/issues"
INDEX_ROW = re.compile(r"(?m)^\| \[.+?\]\(([\w-]+)/\) \| .+? \| (`[\w-]+`|Terminal only) \| .+? \|$")
SHOT = re.compile(r"!\[[^\]]+\]\(\.\./\.\./docs/product-walkthrough-shots/([\w-]+)-desktop\.webp\)")


def test_each_lab_has_the_learner_shape():
    screens = dict(INDEX_ROW.findall((ROOT / "labs" / "README.md").read_text()))
    labs = sorted(path.parent.name for path in (ROOT / "labs").glob("*/README.md"))
    assert sorted(screens) == labs, "labs/README.md must have one row, with a Screen, for every lab"
    for lab in labs:
        text = (ROOT / "labs" / lab / "README.md").read_text()
        for heading in LEARNER_SECTIONS:
            assert f"\n{heading}\n" in text, f"{lab}: missing {heading}"
        assert text.count("```mermaid") == 1, f"{lab}: needs exactly one Mermaid diagram"
        check = text.split("## Check yourself")[1].split("\n## ")[0]
        assert check.count("<details>") >= 2 and check.count("<summary>") == check.count("<details>"), lab
        assert re.search(rf"\]\({re.escape(ISSUES)}[/?]", text.split("## Try next")[1]), f"{lab}: Try next needs a learner issue link"
        shots = SHOT.findall(text)
        if screens[lab] == "Terminal only":
            assert not shots and "Expect:" in text, f"{lab}: a terminal-only lab shows its Expect line"
        else:
            assert shots == [screens[lab].strip("`")], f"{lab}: shows {shots}, labs/README.md names {screens[lab]}"
            assert (ROOT / "docs" / "product-walkthrough-shots" / f"{shots[0]}-desktop.webp").exists(), lab
