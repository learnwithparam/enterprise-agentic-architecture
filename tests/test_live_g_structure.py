"""Live labs 04, 05 and 06. Agent answers have a fixed shape, tools have schemas, and no agent can run a shell."""

import ast
import re
from pathlib import Path

from hcpagents import agents, guards, mcp_server

SRC = Path(__file__).resolve().parents[1] / "src" / "hcpagents"
SHELL_WORDS = re.compile(r"(bash|shell|exec|subprocess|system|terminal|eval|run_command|popen)", re.IGNORECASE)


def objects(schema):
    """Every object schema inside a schema."""
    found = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            found.append(schema)
        for value in schema.values():
            found.extend(objects(value))
    if isinstance(schema, list):
        for value in schema:
            found.extend(objects(value))
    return found


def test_every_agent_answer_is_a_closed_object_that_requires_each_field_it_names():
    for name, spec in agents.AGENTS.items():
        shapes = objects(spec["schema"])
        assert shapes, name
        for shape in shapes:
            assert shape["additionalProperties"] is False, name
            assert set(shape["required"]) == set(shape["properties"]), name


def test_no_agent_tool_or_mcp_tool_can_run_a_shell():
    names = set(guards.ALLOWED_TOOLS) | set(mcp_server.TOOLS)
    names |= {name for name, spec in agents.AGENTS.items() if spec.get("tools")}
    tree = ast.parse((SRC / "agents_options.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "tool":
            names.add(node.args[0].value)
    assert names and not [name for name in names if SHELL_WORDS.search(name)], sorted(names)
    assert guards.ALLOWED_TOOLS == {"mcp__mi__search_approved_content", "mcp__mi__get_block"}


def test_the_agent_tools_are_the_two_read_only_content_tools():
    tree = ast.parse((SRC / "agents_options.py").read_text())
    declared = [node.args[0].value for node in ast.walk(tree)
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "tool"]
    assert sorted(declared) == ["get_block", "search_approved_content"]
    assert {f"mcp__mi__{name}" for name in declared} == guards.ALLOWED_TOOLS


def test_the_agent_modules_import_nothing_that_can_start_a_process():
    for name in ("agents.py", "agents_options.py", "agents_spec.py", "agents_tools.py", "guards.py"):
        imports = [node for node in ast.walk(ast.parse((SRC / name).read_text())) if isinstance(node, (ast.Import, ast.ImportFrom))]
        modules = {alias.name.split(".")[0] for node in imports for alias in node.names}
        modules |= {node.module.split(".")[0] for node in imports if isinstance(node, ast.ImportFrom) and node.module}
        assert not modules & {"subprocess", "pty", "shlex"}, name
