"""The readable gate flags hard-to-read code, and the code in src and labs passes it."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_readable", ROOT / "scripts" / "check_readable.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

BAD_CODE = '''
def f(c, ctx):
    total = lambda b: b + 1
    if (n := c) > 1:
        return total(n) if ctx else None
    return [a for x in c for a in x]
'''


def problems_for(tmp_path, source):
    path = tmp_path / "sample.py"
    path.write_text(source)
    return [message for _, message in gate.problems_in(path)]


def test_short_names_and_abbreviations_are_flagged(tmp_path):
    messages = problems_for(tmp_path, BAD_CODE)
    assert any('"c" is too short' in message for message in messages)
    assert any('"ctx" is an abbreviation' in message for message in messages)


def test_lambda_walrus_one_line_if_and_two_loop_comprehensions_are_flagged(tmp_path):
    messages = problems_for(tmp_path, BAD_CODE)
    for expected in ("lambda", "walrus", "one-line if/else", "two loops"):
        assert any(expected in message for message in messages), expected


def test_a_long_function_and_a_hard_comment_are_flagged(tmp_path):
    body = "\n".join(f"    value_{number} = {number}" for number in range(45))
    source = f"def long_one():\n    # We utilize this value.\n{body}\n"
    messages = problems_for(tmp_path, source)
    assert any("long_one is" in message for message in messages)
    assert any("utilize" in message for message in messages)


def test_plain_code_passes(tmp_path):
    source = "def add_one(number):\n    # Add one to the number.\n    return number + 1\n"
    assert problems_for(tmp_path, source) == []


def test_the_whole_codebase_reads_plainly():
    found = []
    for folder in gate.FOLDERS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            found.extend(f"{path.name}:{line}: {message}" for line, message in gate.problems_in(path))
    assert found == []
