"""The assembler's plan as a LangGraph: select blocks, check they cover every question, and try once more if not.

LangGraph runs only the thinking inside the `assemble` step. The kernel (kernel.py) still owns which steps
exist, and it bounds this graph's loop. Nothing here sets a fact or a route; it returns a selection that the
grounding verifier checks next (ADR 0014).
"""

import json
from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from hcpagents import kernel

MAX_ATTEMPTS = 2
# What the compiled graph may do. tests/test_plan.py proves the graph and this table agree.
EDGES = {("__start__", "select"), ("select", "check"), ("check", "select"), ("check", "__end__")}

Ask = Callable[[str], Awaitable[tuple[dict, set[str]]]]  # prompt -> (agent output, block ids a tool returned)


class State(TypedDict):
    attempt: int
    seen: set[str]
    answers: list[dict]
    uncovered: list[str]
    rejected: list[str]


def _prompt(product: str, country: str, questions: list[dict], retry: list[str]) -> str:
    body = {"product": product, "country": country, "questions": [{"text": q["text"], "topic": q["topic"]} for q in questions]}
    if retry:
        body["retry"] = {"not_covered": retry, "note": "Search again for these using different words from the question."}
    return json.dumps(body)


def build(ask: Ask, product: str, country: str, questions: list[dict], content: dict[str, dict]):
    async def select(s: State) -> dict:
        kernel.check_attempt(s["attempt"] + 1, MAX_ATTEMPTS)
        out, seen = await ask(_prompt(product, country, questions, s["uncovered"]))
        seen = s["seen"] | seen
        answers, rejected = [], list(s["rejected"])
        for a in out["answers"]:
            # Only ids a permitted tool call returned, for this product and country, survive.
            ok = [b for b in a["block_ids"] if b in seen and b in content
                  and content[b]["product"] == product and content[b]["country"] == country]
            rejected += [b for b in a["block_ids"] if b not in ok]
            answers.append({"question": a["question"], "block_ids": ok})
        return {"attempt": s["attempt"] + 1, "seen": seen, "answers": answers, "rejected": rejected,
                "uncovered": list(out["uncovered"])}

    async def check(s: State) -> dict:
        empty = [a["question"] for a in s["answers"] if not a["block_ids"]]
        return {"uncovered": list(dict.fromkeys(s["uncovered"] + empty))}

    def again(s: State) -> str:
        return "select" if s["uncovered"] and s["attempt"] < MAX_ATTEMPTS else END

    g = StateGraph(State)
    g.add_node("select", select)
    g.add_node("check", check)
    g.add_edge(START, "select")
    g.add_edge("select", "check")
    g.add_conditional_edges("check", again, {"select": "select", END: END})
    return g.compile()


async def run(ask: Ask, product: str, country: str, questions: list[dict], content: dict[str, dict]) -> dict:
    final = await build(ask, product, country, questions, content).ainvoke(
        {"attempt": 0, "seen": set(), "answers": [], "uncovered": [], "rejected": []})
    return {"answers": final["answers"], "uncovered": final["uncovered"], "rejected_ids": final["rejected"], "attempts": final["attempt"]}
