"""Assemble a reply from approved blocks and prove each sentence came from one.

The model never writes medical text. It picks block ids. The compose function places those blocks word for word
between the fixed templates, the safety information and the AI note. The verify function then checks the final text
one sentence at a time against the content store as it is now. So a block withdrawn after drafting fails the check at send time.
"""

import re

from hcpagents.world import TODAY, country, is_current, why_not_current

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [piece.strip() for piece in SENTENCE.split(text.strip()) if piece.strip()]


def required_ids(product: str, country_code: str) -> list[str]:
    return ["TPL-OPEN", f"ISI-{product}-{country_code}", country(country_code)["ai_disclosure"], "TPL-CLOSE"]


def compose(product: str, country_code: str, answer_ids: list[str], store: dict[str, dict]) -> list[dict]:
    """The reply in order. It has an opening, the chosen blocks, safety facts, a note and a close."""
    opening, isi, disclosure, closing = required_ids(product, country_code)
    order = [opening, *dict.fromkeys(answer_ids), isi, disclosure, closing]
    return [
        {"block_id": block_id, "version": store[block_id]["version"], "text": store[block_id]["text"],
         "role": _role(block_id, answer_ids)}
        for block_id in order
        if block_id in store
    ]


def _role(block_id: str, answer_ids: list[str]) -> str:
    if block_id in answer_ids:
        return "answer"
    if block_id.startswith("ISI-"):
        return "safety"
    if block_id.startswith("TPL-AI-"):
        return "disclosure"
    return "template"


def render(segments: list[dict]) -> str:
    return " ".join(segment["text"] for segment in segments)


def _evidence(sentence: str, sources: list[dict], today) -> tuple[dict, str | None]:
    """The evidence row for one sentence, and the problem text if it is not grounded."""
    live = [block for block in sources if is_current(block, today)]
    if live:
        block = live[0]
        return {"sentence": sentence, "ok": True, "block_id": block["id"], "version": block["version"],
                "mlr_ref": block["mlr_ref"]}, None
    if sources:
        reason = why_not_current(sources[0], today)
        block_id = sources[0]["id"]
    else:
        reason = "not found in any approved block for this product and country"
        block_id = None
    return {"sentence": sentence, "ok": False, "block_id": block_id, "reason": reason}, f"Ungrounded sentence: {reason}"


def _segment_problems(segments: list[dict], product: str, country_code: str, store: dict[str, dict], today) -> list[str]:
    problems = []
    used = {segment["block_id"] for segment in segments}
    for required_id in required_ids(product, country_code):
        if required_id not in used:
            problems.append(f"Required block {required_id} is missing")
    for segment in segments:
        block = store.get(segment["block_id"])
        if block is None:
            problems.append(f"{segment['block_id']} does not exist")
        elif block["version"] != segment["version"]:
            problems.append(f"{segment['block_id']} changed from v{segment['version']} to v{block['version']} after drafting")
        elif not is_current(block, today):
            problems.append(why_not_current(block, today))
    return problems


def verify(segments: list[dict], product: str, country_code: str, store: dict[str, dict], today=TODAY) -> dict:
    """Check the reply against the store. Gives back evidence for each sentence and the list of problems."""
    allowed = [
        block for block in store.values()
        if block["country"] in (country_code, "ALL") and block["product"] in (product, "ALL")
    ]
    index: dict[str, list[dict]] = {}
    for block in allowed:
        for sentence in sentences(block["text"]):
            index.setdefault(sentence, []).append(block)

    problems: list[str] = []
    evidence = []
    for sentence in sentences(render(segments)):
        row, problem = _evidence(sentence, index.get(sentence, []), today)
        evidence.append(row)
        if problem:
            problems.append(problem)
    problems += _segment_problems(segments, product, country_code, store, today)
    return {"grounded": not problems, "sentences": evidence, "problems": list(dict.fromkeys(problems))}
