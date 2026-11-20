"""The two tools the assembler agent may call. Both only read approved content."""

from hcpagents import retrieval, world
from hcpagents.guards import post_tool

SEARCH_RESULTS = 4  # Blocks one search returns. Enough to compare, few enough to read.


def search(product: str, country: str, query: str, audience: str = "doctor") -> list[dict]:
    """The best current blocks for a question, found behind the facet gate (ADR 0012)."""
    return [{key: block[key] for key in ("block_id", "version", "topic", "text")}
            for block in retrieval.search(query, product, country, k=SEARCH_RESULTS, audience=audience)]


def get_block(store: dict, block_id: str) -> list[dict]:
    block = store.get(block_id)
    if not block or not world.is_current(block):
        return []
    return [{"block_id": block["id"], "version": block["version"], "topic": block["topic"], "text": block["text"]}]


def run_tool(store: dict, tool: str, tool_input: dict, audience: str = "doctor") -> list[dict]:
    if tool == "mcp__mi__search_approved_content":
        query = tool_input.get("query") or tool_input.get("topic", "")
        return search(tool_input.get("product", ""), tool_input.get("country", ""), query, audience)
    return get_block(store, tool_input.get("block_id", ""))


def checked_output(tool: str, tool_input: dict, case: dict, store: dict, audit) -> list[dict]:
    """What the model may read from a tool. Blocks that fail the check after the tool ran are dropped and go to the ledger."""
    kept, dropped = post_tool(run_tool(store, tool, tool_input, world.audience_of(case)), case, store)
    if dropped:
        audit({"type": "tool_output_dropped", "tool": tool, "input": tool_input, "dropped": dropped})
    return kept
