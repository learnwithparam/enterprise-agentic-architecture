"""What a model reads each call is counted and kept under a token budget.

An inquiry may carry the earlier messages of its thread. The model reads the question and as many of those
messages as fit. The oldest go first. The question and the newest message always stay. The summary is never
made by a model. The ledger notes how many messages were dropped, and the full thread stays in the case.
If the question and the newest message alone are too big, the case goes to a person. Nothing is cut inside a message.
"""

import hashlib
import math

from hcpagents import agents

CONTEXT_BUDGET_TOKENS = 3000  # What one agent call may read from the thread. Far below any model window.
TOKENS_PER_WORD = 4 / 3
CHARACTERS_PER_TOKEN = 4


class ContextTooLarge(agents.EscalateToHuman):
    """The question and the newest message do not fit the budget. A person reads the case."""

    rule = "context_too_large"


def count_tokens(text: str) -> int:
    """A safe guess. Each model counts a little differently, so this takes the larger of two counts."""
    by_characters = len(text) / CHARACTERS_PER_TOKEN
    by_words = len(text.split()) * TOKENS_PER_WORD
    return math.ceil(max(by_characters, by_words))


def turn_text(turn: dict) -> str:
    return f"{turn['from']}: {turn['text']}"


def thread_sha(thread: list[dict]) -> str:
    """A short fingerprint of the full thread, so the ledger can show what was and was not read."""
    return hashlib.sha256("\n".join(turn_text(turn) for turn in thread).encode()).hexdigest()[:16]


def fit_thread(thread: list[dict], question: str, budget: int = CONTEXT_BUDGET_TOKENS) -> dict:
    """Keep the question and the newest message. Then add older messages, newest first, while they fit."""
    # Step 1: the question and the newest message must stay.
    must = count_tokens(question)
    if thread:
        must += count_tokens(turn_text(thread[-1]))
    if must > budget:
        raise ContextTooLarge(f"The question and the newest message need {must} tokens; the budget is {budget}")
    # Step 2: walk back from the newest message and stop at the first one that does not fit.
    used = must
    kept = thread[-1:]
    for turn in reversed(thread[:-1]):
        cost = count_tokens(turn_text(turn))
        if used + cost > budget:
            break
        used += cost
        kept = [turn, *kept]
    return {"kept": kept, "dropped": len(thread) - len(kept), "tokens": used}


def model_text(inquiry: dict, budget: int = CONTEXT_BUDGET_TOKENS) -> tuple[str, dict]:
    """The text the model reads for this inquiry, and a note on what was trimmed. No thread means the text as it is."""
    thread = inquiry.get("thread") or []
    if not thread:
        return inquiry["text"], {"thread_turns": 0, "dropped": 0, "tokens": count_tokens(inquiry["text"])}
    fitted = fit_thread(thread, inquiry["text"], budget)
    lines = [turn_text(turn) for turn in fitted["kept"]]
    text = "Earlier messages in this thread, oldest first:\n" + "\n".join(lines) + "\n\nNewest message:\n" + inquiry["text"]
    note = {"thread_turns": len(thread), "dropped": fitted["dropped"], "tokens": fitted["tokens"], "thread_sha256": thread_sha(thread)}
    return text, note
