"""A reply that fails the grounding check gets exactly one redraft. Then a person reviews it.

The model never writes the reply. A redraft means it picks blocks again, this time told what failed.
The same check reads the new pick. If it fails, or no usable block comes back, the case is not grounded.
The routing table then sends it to a reviewer. There is no third try, so a stubborn pick cannot loop.
"""

import json
from collections.abc import Awaitable, Callable

from hcpagents import world

Check = Callable[[list[str]], tuple[list[dict], dict]]  # Takes block ids. Returns the reply segments and the verdict.
Redraft = Callable[[list[str]], Awaitable[list[str]]]  # Takes the problems. Returns the block ids it chose again.

NOTE = "The last reply failed the check for the reasons listed. Choose blocks again. Use only blocks a search returns now."


def redraft_prompt(product: str, country: str, questions: list[dict], problems: list[str]) -> str:
    body = {"product": product, "country": country,
            "questions": [{"text": question["text"], "topic": question["topic"]} for question in questions],
            "redraft": {"problems": problems, "note": NOTE}}
    return json.dumps(body)


def usable_ids(out: dict, seen: set[str], content: dict[str, dict], product: str, country: str, asked: int) -> list[str]:
    """The ids of a redraft. You get none unless every question has a current block that a tool returned."""
    chosen: list[str] = []
    if len(out["answers"]) < asked:
        return chosen
    for answer in out["answers"]:
        kept = [block_id for block_id in answer["block_ids"] if _usable(block_id, seen, content, product, country)]
        if not kept:
            return []
        chosen.extend(kept)
    return chosen


def _usable(block_id: str, seen: set[str], content: dict[str, dict], product: str, country: str) -> bool:
    block = content.get(block_id)
    if block_id not in seen or block is None:
        return False
    return block["product"] == product and block["country"] == country and world.is_current(block)


async def verify_with_one_redraft(ids: list[str], check: Check, redraft: Redraft) -> dict:
    """Check the reply. If it fails, redraft once and check again. The second verdict stands."""
    # Step 1: check the first reply.
    segments, verification = check(ids)
    if verification["grounded"]:
        return {"segments": segments, "verification": verification, "redrafts": 0, "first_problems": []}
    # Step 2: redraft once, told what failed.
    first_problems = verification["problems"]
    new_ids = await redraft(first_problems)
    if not new_ids:
        failed = verification | {"grounded": False, "problems": [*first_problems, "The redraft chose no usable block"]}
        return {"segments": segments, "verification": failed, "redrafts": 1, "first_problems": first_problems}
    # Step 3: check the redraft. Its verdict stands, grounded or not.
    segments, verification = check(new_ids)
    return {"segments": segments, "verification": verification, "redrafts": 1, "first_problems": first_problems}
