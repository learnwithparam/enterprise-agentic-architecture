"""Assemble a reply from approved blocks and prove every sentence came from one.

The model never writes medical text. It picks block ids; compose() places those blocks verbatim
between the fixed templates, the safety information and the AI disclosure. verify() then checks
the rendered text sentence by sentence against the content store as it is right now, so a block
withdrawn after drafting fails the check at send time.
"""

import re

from hcpagents.world import TODAY, country, is_current, why_not_current

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text.strip()) if s.strip()]


def required_ids(product: str, country_code: str) -> list[str]:
    return ["TPL-OPEN", f"ISI-{product}-{country_code}", country(country_code)["ai_disclosure"], "TPL-CLOSE"]


def compose(product: str, country_code: str, answer_ids: list[str], store: dict[str, dict]) -> list[dict]:
    """Ordered reply segments: opening, the chosen blocks, safety information, disclosure, closing."""
    opening, isi, disclosure, closing = required_ids(product, country_code)
    order = [opening, *dict.fromkeys(answer_ids), isi, disclosure, closing]
    return [
        {"block_id": b, "version": store[b]["version"], "text": store[b]["text"], "role": _role(b, answer_ids)}
        for b in order
        if b in store
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
    return " ".join(s["text"] for s in segments)


def verify(segments: list[dict], product: str, country_code: str, store: dict[str, dict], today=TODAY) -> dict:
    """Check the reply against the store. Returns per-sentence evidence and the list of problems."""
    allowed = [
        b for b in store.values()
        if b["country"] in (country_code, "ALL") and b["product"] in (product, "ALL")
    ]
    index: dict[str, list[dict]] = {}
    for b in allowed:
        for s in sentences(b["text"]):
            index.setdefault(s, []).append(b)

    problems: list[str] = []
    evidence = []
    for s in sentences(render(segments)):
        sources = index.get(s, [])
        live = [b for b in sources if is_current(b, today)]
        if live:
            b = live[0]
            evidence.append({"sentence": s, "ok": True, "block_id": b["id"], "version": b["version"], "mlr_ref": b["mlr_ref"]})
        else:
            reason = why_not_current(sources[0], today) if sources else "not found in any approved block for this product and country"
            evidence.append({"sentence": s, "ok": False, "block_id": sources[0]["id"] if sources else None, "reason": reason})
            problems.append(f"Ungrounded sentence: {reason}")

    used = {seg["block_id"] for seg in segments}
    for rid in required_ids(product, country_code):
        if rid not in used:
            problems.append(f"Required block {rid} is missing")
    for seg in segments:
        b = store.get(seg["block_id"])
        if b is None:
            problems.append(f"{seg['block_id']} does not exist")
        elif b["version"] != seg["version"]:
            problems.append(f"{seg['block_id']} changed from v{seg['version']} to v{b['version']} after drafting")
        elif not is_current(b, today):
            problems.append(why_not_current(b, today))

    return {"grounded": not problems, "sentences": evidence, "problems": list(dict.fromkeys(problems))}
