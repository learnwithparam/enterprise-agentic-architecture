"""A lead agent gives one small question to a specialist step. It checks the answer before it uses it.

The specialist gets a narrow brief and a copy of it. It never sees the case or the doctor.
The lead accepts only block ids that are in the brief and current. Any other answer is refused and goes on the ledger.
"""

import copy
from collections.abc import Callable

from hcpagents import context, ledger, world


def specialist(brief: dict) -> dict:
    """Name the blocks of the brief that match its topic. It can read nothing outside the brief."""
    chosen = [block["id"] for block in brief["blocks"] if brief["topic"] in (None, block["topic"])]
    return {"block_ids": chosen}


def check(brief: dict, answer: dict, content: dict[str, dict]) -> list[str]:
    """Every reason the answer cannot be used. An empty list means the lead may use it."""
    problems = []
    allowed = {block["id"] for block in brief["blocks"]}
    for block_id in answer.get("block_ids", []):
        block = content.get(block_id)
        if block_id not in allowed:
            problems.append(f"{block_id} was not in the brief")
        elif block is None:
            problems.append(f"{block_id} does not exist")
        elif world.why_not_current(block):
            problems.append(world.why_not_current(block))
    if not answer.get("block_ids"):
        problems.append("The specialist named no block")
    return problems


def delegate(case_id: str, hcp: dict, product: str, topic: str | None, text: str, content: dict[str, dict],
             step: Callable[[dict], dict] = specialist, record: Callable[[dict], object] | None = None) -> dict:
    """Brief the specialist, check what it returns, and write the outcome to the ledger."""
    record = record or ledger.append
    brief = context.for_question(hcp, product, topic, text, content)
    answer = step(copy.deepcopy(brief))
    problems = check(brief, answer, content)
    record({"type": "delegation", "agent": "lead", "to": "specialist", "case": case_id,
            "accepted": not problems, "blocks": answer.get("block_ids", []), "problems": problems})
    usable = answer.get("block_ids", [])
    if problems:
        usable = []
    return {"accepted": not problems, "block_ids": usable, "problems": problems}
