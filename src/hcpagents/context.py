"""Each question gets its own context. It holds the facts of one country and the current blocks of one product.

A case may hold a doctor's contacts and other cases. A question needs none of them.
So the context is built for the question and carries only what the answer needs.
"""

from hcpagents import store, world

FIELDS = ("question", "topic", "product", "country", "facets", "blocks")


def _block_view(block: dict) -> dict:
    return {"id": block["id"], "version": block["version"], "topic": block["topic"], "text": block["text"]}


def _fits(block: dict, product: str, country: str, topic: str | None) -> bool:
    if block["product"] != product or block["country"] != country:
        return False
    if topic and block["topic"] != topic:
        return False
    return world.is_current(block)


def for_question(hcp: dict, product: str, topic: str | None, text: str, content: dict[str, dict] | None = None) -> dict:
    """Only the facets of the doctor's country and the current blocks of this product there. Nothing about the doctor."""
    country = hcp["country"]
    if content is None:
        content = store.content()
    blocks = [_block_view(block) for block in sorted(content.values(), key=_block_id) if _fits(block, product, country, topic)]
    return {"question": text, "topic": topic, "product": product, "country": country,
            "facets": {"country": world.country(country), "scope": world.scope(product, country)}, "blocks": blocks}


def _block_id(block: dict) -> str:
    return block["id"]
