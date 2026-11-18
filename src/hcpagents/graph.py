"""The inquiry graph is a table of routes and a plain engine that walks it.

The model never chooses a route. Each node sets facts. After every node, decide walks the table in order.
It stops at the first rule whose fact is unknown, so it waits for more nodes.
It also stops at the first rule whose fact matches, and that rule is the route.
If every rule passes, the reply is sent. The kernel runs the nodes. It refuses any step the table does not allow.

The same table builds the Step Functions definition. Tests walk every mix of facts through decide.
They also run one case per rule through Step Functions to prove the two agree.
"""

from itertools import product as cartesian

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

# Which node sets which facts, in the order they run.
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
    """Return the route for these facts, or None while a fact the next rule needs is unknown."""
    # Step 1: Walk the rules in order.
    for index, (fact, value, route, why) in enumerate(ROUTING):
        # Step 2: Stop while a fact the rule needs is unknown.
        if fact not in facts:
            return None
        # Step 3: The first rule that matches gives the route.
        if facts[fact] == value:
            return {"route": route, "rule": index, "fact": fact, "why": why}
    # Step 4: No rule matched, so the reply may be sent.
    return {"route": SEND[0], "rule": len(ROUTING), "fact": None, "why": SEND[1]}


def asl() -> dict:
    """Amazon States Language for the routing table. It takes facts and returns a route and a rule."""
    states: dict = {}
    for index, (fact, value, route, _) in enumerate(ROUTING):
        next_state = "Send"
        if index + 1 < len(ROUTING):
            next_state = f"Rule{index + 1}"
        comparison = {"StringEquals": value}
        if isinstance(value, bool):
            comparison = {"BooleanEquals": value}
        states[f"Rule{index}"] = {
            "Type": "Choice",
            "Choices": [
                {"Not": {"Variable": f"$.facts.{fact}", "IsPresent": True}, "Next": "Pending"},
                {"Variable": f"$.facts.{fact}", **comparison, "Next": f"Route{index}"},
            ],
            "Default": next_state,
        }
        states[f"Route{index}"] = {"Type": "Pass", "Result": {"route": route, "rule": index}, "End": True}
    states["Send"] = {"Type": "Pass", "Result": {"route": SEND[0], "rule": len(ROUTING)}, "End": True}
    states["Pending"] = {"Type": "Pass", "Result": {"route": None, "rule": None}, "End": True}
    return {"Comment": "Inquiry routing, generated from hcpagents.graph.ROUTING", "StartAt": "Rule0", "States": states}


def every_fact_combination():
    keys = list(FACTS)
    for values in cartesian(*(FACTS[key] for key in keys)):
        yield dict(zip(keys, values))
