"""Tool-call guards are plain functions, so tests can call them directly.
The agents module wraps them as hooks. Replay runs recorded calls through the same ones."""

from collections.abc import Callable

from hcpagents import world

ALLOWED_TOOLS = {"mcp__mi__search_approved_content", "mcp__mi__get_block"}

# Each call gets the agent, tool, country, product and case. It returns yes or no, and a reason.
Authorize = Callable[[str, str, str, str, dict], tuple[bool, str]]


def pre_tool(agent: str, tool: str, tool_input: dict, case: dict, store: dict, authorize: Authorize) -> tuple[bool, str]:
    """Allow a tool call only when the tool is listed and fits the case country and product."""
    # Step 1: Refuse a tool that is not on the allowlist.
    if tool not in ALLOWED_TOOLS:
        return False, f"{tool} is not on the allowlist"
    # Step 2: Find the country and product the call is about.
    if tool == "mcp__mi__get_block":
        block = store.get(tool_input.get("block_id", ""))
        if block is None:
            return False, f"Block {tool_input.get('block_id')} does not exist"
        country, product = block["country"], block["product"]
        if country == "ALL" and product == "ALL":
            return True, "Template block"
    else:
        country, product = tool_input.get("country", ""), tool_input.get("product", "")
    # Step 3: Refuse a call for another country or product.
    if country != case["country"] or product != case["product"]:
        return False, f"Case is {case['product']} in {case['country']}; the call asked for {product} in {country}"
    # Step 4: Ask Cedar if this agent may call this tool.
    return authorize(agent, tool, country, product, case)


def _fits_case(block: dict, case: dict) -> bool:
    if block["country"] == "ALL" and block["product"] == "ALL":
        return True
    return block["country"] == case["country"] and block["product"] == case["product"]


def post_tool(found: list[dict], case: dict, store: dict) -> tuple[list[dict], list[str]]:
    """Check what a tool returned, after it ran. Returns the blocks to keep and the ids dropped.
    A block that is not current, or is for another country or product, never reaches the model,
    even if the search let it through."""
    kept, dropped = [], []
    for item in found:
        block = store.get(item["block_id"])
        if block and world.is_current(block) and _fits_case(block, case):
            kept.append(item)
        else:
            dropped.append(item["block_id"])
    return kept, dropped


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
