"""Tool-call guards are plain functions, so tests can call them directly.
The agents module wraps them as hooks. Replay runs recorded calls through the same ones."""

from collections.abc import Callable

ALLOWED_TOOLS = {"mcp__mi__search_approved_content", "mcp__mi__get_block"}

# Each call gets the agent, tool, country, product and case. It returns yes or no, and a reason.
Authorize = Callable[[str, str, str, str, dict], tuple[bool, str]]


def pre_tool(agent: str, tool: str, tool_input: dict, case: dict, store: dict, authorize: Authorize) -> tuple[bool, str]:
    """Allow a tool call only when the tool is listed and fits the case country and product."""
    if tool not in ALLOWED_TOOLS:
        return False, f"{tool} is not on the allowlist"
    if tool == "mcp__mi__get_block":
        block = store.get(tool_input.get("block_id", ""))
        if block is None:
            return False, f"Block {tool_input.get('block_id')} does not exist"
        country, product = block["country"], block["product"]
        if country == "ALL" and product == "ALL":
            return True, "Template block"
    else:
        country, product = tool_input.get("country", ""), tool_input.get("product", "")
    if country != case["country"] or product != case["product"]:
        return False, f"Case is {case['product']} in {case['country']}; the call asked for {product} in {country}"
    return authorize(agent, tool, country, product, case)


def audit_entry(agent: str, tool: str, tool_input: dict, allowed: bool, reason: str, result_ids: list[str]) -> dict:
    return {
        "type": "tool_call",
        "agent": agent,
        "tool": tool,
        "input": tool_input,
        "allowed": allowed,
        "reason": reason,
        "returned": result_ids,
    }
