"""Concept 25: the API and MCP act as the signed-in user. No handler reads a service credential."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "hcpagents"
HANDLER_FILES = ("v1.py", "mcp_server.py")
SERVICE_NAMES = {"gateway_keys", "gateway", "key_for", "issue_key", "ssm", "secretsmanager", "tenant_key", "privacy"}
SECRET_WORDS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def tree_of(name: str) -> ast.AST:
    return ast.parse((SRC / name).read_text())


def names_used(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        if isinstance(node, ast.Attribute):
            found.add(node.attr)
        if isinstance(node, ast.alias):
            found.add(node.name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def test_no_api_or_mcp_handler_touches_a_service_credential():
    for name in HANDLER_FILES:
        used = names_used(tree_of(name))
        assert not used & SERVICE_NAMES, (name, sorted(used & SERVICE_NAMES))
        environment = [word for word in used if word.startswith("MI_") and any(part in word for part in SECRET_WORDS)]
        assert not environment, (name, environment)


def route_functions(tree: ast.AST) -> list[ast.FunctionDef]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
            found.append(node)
    return found


def test_every_v1_route_gets_the_caller_from_the_verified_token():
    routes = route_functions(tree_of("v1.py"))
    assert routes
    for route in routes:
        assert "user" in [argument.arg for argument in route.args.args], route.name


def test_every_mcp_tool_asks_who_the_caller_is_before_it_reads_data():
    tree = tree_of("mcp_server.py")
    tools = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in ("list_cases", "get_case", "release_trend")]
    assert len(tools) == 3
    for tool in tools:
        first = ast.unparse(tool.body[1])
        assert "_user(context" in first, tool.name
