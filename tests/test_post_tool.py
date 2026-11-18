"""The check after a tool runs: a block that fails it never reaches the model, and the drop is in the ledger."""

from hcpagents import agents_tools, guards, world

TOOL = "mcp__mi__get_block"


def a_country_block():
    return next(block for block in world.blocks() if block["country"] != "ALL" and world.is_current(block))


def run(block: dict, case: dict, store: dict) -> tuple[list[dict], list[dict]]:
    entries: list[dict] = []
    kept = agents_tools.checked_output(TOOL, {"block_id": block["id"]}, case, store, entries.append)
    return kept, entries


def test_a_block_for_the_cases_own_country_and_product_is_kept():
    block = a_country_block()
    kept, entries = run(block, {"country": block["country"], "product": block["product"]}, {block["id"]: block})
    assert [found["block_id"] for found in kept] == [block["id"]] and entries == []


def test_a_block_for_another_country_is_dropped_and_the_ledger_says_so():
    block = a_country_block()
    other = next(code for code in ("DE", "FR", "US") if code != block["country"])
    kept, entries = run(block, {"country": other, "product": block["product"]}, {block["id"]: block})
    assert kept == []
    assert entries[0]["type"] == "tool_output_dropped" and entries[0]["dropped"] == [block["id"]]


def test_a_block_that_is_no_longer_approved_is_dropped():
    block = a_country_block() | {"status": "withdrawn"}
    found = [{"block_id": block["id"]}]
    kept, dropped = guards.post_tool(found, {"country": block["country"], "product": block["product"]}, {block["id"]: block})
    assert kept == [] and dropped == [block["id"]]


def test_a_block_the_case_store_does_not_hold_is_dropped():
    kept, dropped = guards.post_tool([{"block_id": "b-not-here"}], {"country": "DE", "product": "p"}, {})
    assert kept == [] and dropped == ["b-not-here"]
