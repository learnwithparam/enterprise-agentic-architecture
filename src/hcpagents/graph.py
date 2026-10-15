"""The inquiry graph: an ordered routing table and the deterministic engine that walks it.

The model never chooses a route. Each node establishes facts; after every node the engine walks
ROUTING in order and stops at the first rule whose fact is still unknown (wait for more nodes) or
whose fact matches (that is the route). If every rule passes, the reply is sent.

The same table generates the Step Functions definition deployed to Floci. Tests walk every
combination of facts through decide(), and run one case per rule through Step Functions to prove the two agree.
"""

from collections.abc import Awaitable, Callable
from itertools import product as cartesian
import time

# (fact, value that triggers the route, route, why). Order is the policy: safety first.
ROUTING: list[tuple[str, object, str, str]] = [
    ("ae", True, "pv", "Possible adverse event or special situation. Pharmacovigilance owns it and the AI does not answer."),
    ("verified_hcp", False, "specialist", "The sender is not a verified healthcare professional. A specialist replies."),
    ("injection", True, "decline", "The message tries to change the rules. Nothing is drafted and the attempt is recorded."),
    ("intent", "promotional_request", "decline", "A request for promotional material, not an unsolicited medical question."),
    ("intent", "other", "specialist", "Not a medical question. A specialist decides what to do."),
    ("known_product", False, "specialist", "Not a Quillon product. A specialist replies."),
    ("in_scope", False, "offlabel", "Outside the approved label for this country. Medical writes any reply; the AI drafts nothing."),
    ("covered", False, "review", "Approved content does not cover every question. A medical reviewer completes the reply."),
    ("grounded", False, "review", "A sentence could not be traced to current approved content."),
    ("auto_allowed", False, "review", "These topics are not cleared for automatic replies here. A medical reviewer approves the draft."),
]
SEND = ("send", "On-label, every sentence traced to current approved content, and cleared for automatic replies.")

FACTS: dict[str, tuple] = {
    "ae": (True, False),
    "verified_hcp": (True, False),
    "injection": (True, False),
    "intent": ("medical_question", "promotional_request", "other"),
    "known_product": (True, False),
    "in_scope": (True, False),
    "covered": (True, False),
    "grounded": (True, False),
    "auto_allowed": (True, False),
}

# Which node establishes which facts, in execution order.
NODES: list[tuple[str, tuple[str, ...]]] = [
    ("intake", ("verified_hcp",)),
    ("safety_screen", ("ae",)),
    ("classify", ("intent", "injection", "known_product")),
    ("scope_check", ("in_scope",)),
    ("assemble", ("covered",)),
    ("verify", ("grounded",)),
    ("autonomy", ("auto_allowed",)),
]


def decide(facts: dict) -> dict | None:
    """The route for these facts, or None while a fact the next rule needs is unknown."""
    for i, (fact, value, route, why) in enumerate(ROUTING):
        if fact not in facts:
            return None
        if facts[fact] == value:
            return {"route": route, "rule": i, "fact": fact, "why": why}
    return {"route": SEND[0], "rule": len(ROUTING), "fact": None, "why": SEND[1]}


Node = Callable[[dict], Awaitable[dict]]


async def run(impls: dict[str, Node], ctx: dict) -> dict:
    """Run nodes in order until a route is decided. Each node returns {"facts": {...}, ...detail}."""
    facts: dict = {}
    trace: list[dict] = []
    for name, produces in NODES:
        start = time.perf_counter()
        out = await impls[name](ctx)
        missing = set(produces) - set(out["facts"])
        if missing:
            raise ValueError(f"node {name} did not establish {sorted(missing)}")
        facts.update(out["facts"])
        ctx.setdefault("facts", {}).update(out["facts"])
        trace.append({"node": name, "ms": round((time.perf_counter() - start) * 1000, 1), **out})
        decision = decide(facts)
        if decision:
            return {"decision": decision, "facts": facts, "trace": trace}
    raise RuntimeError("graph finished without a decision")


def asl() -> dict:
    """Amazon States Language for the routing table. Input: {"facts": {...}}; output: {"route", "rule"}."""
    states: dict = {}
    for i, (fact, value, route, _) in enumerate(ROUTING):
        nxt = f"Rule{i + 1}" if i + 1 < len(ROUTING) else "Send"
        cmp = {"BooleanEquals": value} if isinstance(value, bool) else {"StringEquals": value}
        states[f"Rule{i}"] = {
            "Type": "Choice",
            "Choices": [
                {"Not": {"Variable": f"$.facts.{fact}", "IsPresent": True}, "Next": "Pending"},
                {"Variable": f"$.facts.{fact}", **cmp, "Next": f"Route{i}"},
            ],
            "Default": nxt,
        }
        states[f"Route{i}"] = {"Type": "Pass", "Result": {"route": route, "rule": i}, "End": True}
    states["Send"] = {"Type": "Pass", "Result": {"route": SEND[0], "rule": len(ROUTING)}, "End": True}
    states["Pending"] = {"Type": "Pass", "Result": {"route": None, "rule": None}, "End": True}
    return {"Comment": "Inquiry routing, generated from hcpagents.graph.ROUTING", "StartAt": "Rule0", "States": states}


def every_fact_combination():
    keys = list(FACTS)
    for values in cartesian(*(FACTS[k] for k in keys)):
        yield dict(zip(keys, values))
