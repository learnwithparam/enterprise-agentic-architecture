"""The assembler plan as a LangGraph. It picks blocks, checks they cover each question, and tries once more if not.

LangGraph runs only the thinking inside the assemble step. The kernel still owns which steps exist.
The kernel also limits the loop of this graph.
Nothing here sets a fact or a route. It returns a pick that the grounding check reads next (ADR 0014).
"""

import json
from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from hcpagents import kernel

MAX_ATTEMPTS = 2
# What the built graph may do. A test proves the graph and this table agree.
EDGES = {("__start__", "select"), ("select", "check"), ("check", "select"), ("check", "__end__")}

Ask = Callable[[str], Awaitable[tuple[dict, set[str]]]]  # Takes a prompt. Returns the agent output and the block ids a tool returned.


class State(TypedDict):
    attempt: int
    seen: set[str]
    answers: list[dict]
    uncovered: list[str]
    rejected: list[str]


def _prompt(product: str, country: str, questions: list[dict], retry: list[str], rejected: list[str] | None = None) -> str:
    body = {"product": product, "country": country,
            "questions": [{"text": question["text"], "topic": question["topic"]} for question in questions]}
    if retry:
        body["retry"] = {"not_covered": retry, "note": "Search again for these using different words from the question."}
    if retry and rejected:
        body["retry"]["refused_ids"] = sorted(set(rejected))
        body["retry"]["refused_note"] = ("These ids were refused. A search did not return them for this product and country. "
                                         "Choose only ids a search returns.")
    return json.dumps(body)


def build(ask: Ask, product: str, country: str, questions: list[dict], content: dict[str, dict]):
    async def select(state: State) -> dict:
        kernel.check_attempt(state["attempt"] + 1, MAX_ATTEMPTS)
        out, seen = await ask(_prompt(product, country, questions, state["uncovered"], state["rejected"]))
        seen = state["seen"] | seen
        answers, rejected = [], list(state["rejected"])
        for answer in out["answers"]:
            # Keep only ids that a tool call returned for this product and country.
            kept = [block for block in answer["block_ids"] if block in seen and block in content
                    and content[block]["product"] == product and content[block]["country"] == country]
            rejected += [block for block in answer["block_ids"] if block not in kept]
            answers.append({"question": answer["question"], "block_ids": kept})
        return {"attempt": state["attempt"] + 1, "seen": seen, "answers": answers, "rejected": rejected,
                "uncovered": list(out["uncovered"])}

    async def check(state: State) -> dict:
        empty = [answer["question"] for answer in state["answers"] if not answer["block_ids"]]
        return {"uncovered": list(dict.fromkeys(state["uncovered"] + empty))}

    def again(state: State) -> str:
        if state["uncovered"] and state["attempt"] < MAX_ATTEMPTS:
            return "select"
        return END

    graph = StateGraph(State)
    graph.add_node("select", select)
    graph.add_node("check", check)
    graph.add_edge(START, "select")
    graph.add_edge("select", "check")
    graph.add_conditional_edges("check", again, {"select": "select", END: END})
    return graph.compile()


async def run(ask: Ask, product: str, country: str, questions: list[dict], content: dict[str, dict]) -> dict:
    final = await build(ask, product, country, questions, content).ainvoke(
        {"attempt": 0, "seen": set(), "answers": [], "uncovered": [], "rejected": []})
    return {"answers": final["answers"], "uncovered": final["uncovered"], "rejected_ids": final["rejected"], "attempts": final["attempt"]}
