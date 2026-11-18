"""Each lab README lists the `# Step` comments of one real function. The list must match the code."""

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
