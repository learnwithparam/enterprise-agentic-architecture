"""Check email copy against approved text.

A sentence passes if a live block for that product and country says it.
Any other sentence is flagged.
"""

from difflib import SequenceMatcher

from hcpagents import grounding, store
from hcpagents.world import TODAY

CLOSE = 0.95  # how alike two sentences must be to count as the same sentence


def _alike(first: str, second: str) -> float:
    return SequenceMatcher(None, first.lower(), second.lower()).ratio()


def _best(sentence: str, blocks: list[dict]) -> tuple[dict, str] | None:
    """The block sentence closest to this one, if any is close enough."""
    best, best_score = None, CLOSE
    for block in blocks:
        for piece in grounding.sentences(block["text"]):
            score = _alike(sentence, piece)
            if score >= best_score:
                best, best_score = (block, piece), score
    return best


def _block_id(block: dict) -> str:
    return block["id"]


def _allowed(block: dict, product: str, country: str) -> bool:
    return block["country"] in (country, "ALL") and block["product"] in (product, "ALL")


def _one(sentence: str, product: str, country: str, content: dict[str, dict]) -> dict:
    blocks = sorted(content.values(), key=_block_id)
    home = [block for block in blocks if _allowed(block, product, country)]
    found = _best(sentence, home)
    if found is None:
        if _best(sentence, blocks):
            return {"text": sentence, "status": "wrong_country", "block_id": None}
        return {"text": sentence, "status": "unapproved", "block_id": None}
    block, piece = found
    segment = {"block_id": block["id"], "version": block["version"], "text": piece}
    row = grounding.verify([segment], product, country, content, TODAY)["sentences"][0]
    status = "approved"
    if not row["ok"]:
        status = "withdrawn"
    return {"text": sentence, "status": status, "block_id": block["id"]}


def check_copy(text: str, product: str, country: str) -> dict:
    """Each sentence of the copy with its status. The copy is ok only when every sentence is approved."""
    content = store.content()
    rows = [_one(sentence, product, country, content) for sentence in grounding.sentences(text)]
    return {"ok": bool(rows) and all(row["status"] == "approved" for row in rows), "sentences": rows}
