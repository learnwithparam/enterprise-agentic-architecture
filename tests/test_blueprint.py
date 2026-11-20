"""docs/blueprint.md is pinned to the code. A table that drifts from the code fails here."""

import ast
import re
import tomllib
from pathlib import Path

from hcpagents import store

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = (ROOT / "docs" / "blueprint.md").read_text()
CEDAR = (ROOT / "policies" / "cedar" / "zones.cedar").read_text()


def roles_in_world() -> set[str]:
    return {user["role"] for user in tomllib.loads((ROOT / "world" / "people.toml").read_text())["user"]}


def table_after(heading_text: str) -> list[list[str]]:
    """The rows of the first table that follows this text, without the header and the rule line."""
    start = BLUEPRINT.index(heading_text)
    rows = []
    for line in BLUEPRINT[start:].splitlines():
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
        elif rows:
            break
    return rows[2:]


def test_the_view_matrix_matches_cedar_and_covers_every_role():
    medical_roles = set(re.findall(r'principal\.role == "(\w+)"', CEDAR))
    in_doc = {role: view for role, view, _what in table_after("Who gets which view")}
    roles = roles_in_world()
    assert set(in_doc) == roles
    for role, view in in_doc.items():
        assert view == ("medical" if role in medical_roles else "commercial"), role


def test_the_audience_table_matches_the_content_blocks():
    seen = {}
    for block in store_blocks():
        seen.setdefault(block["doc_type"], set()).update(block["audience"])
    audience_names = ("doctor", "rep", "chatbot")
    for doc_type, *flags in table_after("What may be said to whom"):
        allowed = {name for name, flag in zip(audience_names, flags, strict=True) if flag == "yes"}
        assert seen[doc_type] == allowed, doc_type
    assert set(seen) == {row[0] for row in table_after("What may be said to whom")}


def store_blocks() -> list[dict]:
    found = []
    for path in [ROOT / "world" / "content.toml", *(ROOT / "world" / "tenants").glob("*/content.toml")]:
        found += tomllib.loads(path.read_text())["block"]
    return found


def functions_of(module: str) -> set[str]:
    tree = ast.parse((ROOT / "src" / "hcpagents" / module).read_text())
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_every_approval_point_names_a_function_that_exists():
    rows = table_after("Every place a human decides")
    assert len(rows) >= 8
    for _decision, _role, code in rows:
        module, function = code.strip("`").split("::")
        assert function in functions_of(module), code


def test_every_approval_role_is_a_real_role():
    roles = roles_in_world()
    for _decision, role, _code in table_after("Every place a human decides"):
        assert role in roles, role


def test_the_zones_in_the_diagram_are_the_zones_in_the_store():
    for zone in store.ZONES:
        assert f"hcp_{zone}" in BLUEPRINT, zone
    assert set(store.ZONES) == {"medical", "safety", "commercial"}


def test_the_blueprint_has_the_four_diagrams_and_a_legend_for_each():
    assert BLUEPRINT.count("```mermaid") == 4
    assert BLUEPRINT.count("**Legend.**") == 4


def test_the_known_limits_are_written_down():
    assert "no holiday calendar" in BLUEPRINT and "English text only" in BLUEPRINT


def test_every_test_named_in_common_mistakes_exists():
    text = (ROOT / "docs" / "common-mistakes.md").read_text()
    paths = re.findall(r"`((?:tests|labs)/[\w./-]+?\.py)(?:::(\w+))?`", text)
    assert len(paths) >= 9
    for path, name in paths:
        source = (ROOT / path).read_text()
        assert not name or f"def {name}(" in source, (path, name)
