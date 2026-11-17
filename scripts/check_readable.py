"""Fail when the code does not read like plain English. Wired into make check.

A Python port of the live-labs readable and plain-code gates. It reads src/ and labs/.

Rules:
- Names are whole words. No abbreviations. No names of two letters or fewer, except i, id, ok and _.
- No lambda, no walrus, no one-line if/else, no comprehension with two loops.
- A file is at most 300 lines. A function is at most 40 lines.
- A comment or docstring sentence is at most 25 words and uses no hard word.
- A comment or docstring reads at grade 6.5 or lower.
"""

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ["src/hcpagents", "labs"]

LONGEST_FILE = 300
LONGEST_FUNCTION = 40
LONGEST_SENTENCE = 25
HIGHEST_GRADE = 6.5
SHORT_NAMES_THAT_ARE_FINE = {"i", "id", "ok", "_", "s3"}
ABBREVIATIONS = {
    "ctx", "cfg", "tmp", "res", "req", "resp", "obj", "arr", "val", "str", "num",
    "idx", "cnt", "msg", "fn", "cb", "evt", "buf", "acc", "elem", "mgr", "svc",
}
HARD_WORDS = ["utilize", "facilitate", "commence", "subsequently", "approximately", "prior to"]


def name_problem(name: str) -> str:
    if name in ABBREVIATIONS:
        return f'"{name}" is an abbreviation; write the whole word'
    if len(name) <= 2 and name not in SHORT_NAMES_THAT_ARE_FINE:
        return f'"{name}" is too short; name what it holds in a whole word'
    return ""


def count_syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def grade_of(text: str) -> float:
    sentences = [s for s in re.split(r"[.!?]\s|[.!?]$", text) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words:
        return 0.0
    syllables = sum(count_syllables(word) for word in words)
    return 0.39 * len(words) / len(sentences) + 11.8 * syllables / len(words) - 15.59


def prose_problems(text: str) -> list[str]:
    problems = []
    for sentence in re.split(r"[.!?:]\s", text):
        words = sentence.split()
        if len(words) > LONGEST_SENTENCE:
            problems.append(f"sentence has {len(words)} words; keep it under {LONGEST_SENTENCE + 1}")
    for word in HARD_WORDS:
        if word in text.lower():
            problems.append(f'"{word}" is a hard word; use a simpler one')
    if len(text.split()) >= 8 and grade_of(text) > HIGHEST_GRADE:
        problems.append(f"reads at grade {grade_of(text):.1f}; keep it at {HIGHEST_GRADE} or lower")
    return problems


def names_declared(tree: ast.AST) -> list[tuple[str, int]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.name, node.lineno))
        if isinstance(node, ast.arg):
            found.append((node.arg, node.lineno))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.append((node.id, node.lineno))
        if isinstance(node, ast.ExceptHandler) and node.name:
            found.append((node.name, node.lineno))
    return found


def syntax_problems(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            found.append((node.lineno, "lambda is not allowed; write a named function"))
        if isinstance(node, ast.NamedExpr):
            found.append((node.lineno, "walrus is not allowed; use two lines"))
        if isinstance(node, ast.IfExp):
            found.append((node.lineno, "one-line if/else is not allowed; use if and else"))
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            if len(node.generators) > 1:
                found.append((node.lineno, "a comprehension with two loops is not allowed; use for loops"))
    return found


def function_length_problems(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > LONGEST_FUNCTION:
                found.append((node.lineno, f"{node.name} is {length} lines; keep it under {LONGEST_FUNCTION + 1}"))
    return found


def docstring_problems(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            text = ast.get_docstring(node)
            if text:
                line = getattr(node, "lineno", 1)
                for paragraph in text.split("\n\n"):
                    flat = " ".join(paragraph.split())
                    found.extend((line, message) for message in prose_problems(flat))
    return found


def comment_problems(source: str) -> list[tuple[int, str]]:
    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            text = token.string.lstrip("#").strip()
            found.extend((token.start[0], message) for message in prose_problems(text))
    return found


def problems_in(path: Path) -> list[tuple[int, str]]:
    source = path.read_text()
    tree = ast.parse(source)
    found = []
    if source.count("\n") + 1 > LONGEST_FILE:
        found.append((1, f"file is {source.count(chr(10)) + 1} lines; keep it under {LONGEST_FILE + 1}"))
    for name, line in names_declared(tree):
        message = name_problem(name)
        if message:
            found.append((line, message))
    found.extend(syntax_problems(tree))
    found.extend(function_length_problems(tree))
    found.extend(docstring_problems(tree))
    found.extend(comment_problems(source))
    return sorted(set(found))


def main() -> int:
    files = []
    for folder in FOLDERS:
        files.extend(sorted((ROOT / folder).rglob("*.py")))
    total = 0
    for path in files:
        for line, message in problems_in(path):
            print(f"{path.relative_to(ROOT)}:{line}: {message}")
            total += 1
    print(f"readable: {total} problems in {len(files)} files")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
