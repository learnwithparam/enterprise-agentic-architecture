"""This router picks which of two models answers a call, or hands it to a person.

It looks at the task, the risk, the budget left and how past tries went.
The order is Haiku, then Sonnet, then a person. No other model is ever returned.
It is a plain function, so the eval gate can run it whole (ADR 0008).
"""

from dataclasses import dataclass

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"

# Narrow work in large volume stays on Haiku. Open work that weighs options goes to Sonnet.
HAIKU_TASKS = frozenset({"screen", "classify", "select"})
SONNET_TASKS = frozenset({"plan", "arbitrate", "synthesize", "optimize"})
RISKS = ("low", "high")
SONNET_CALL_ESTIMATE_USD = 0.01  # What one Sonnet call may cost. Below this budget a person takes over.

SCHEMA_FAILURE = "schema_failure"
LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class Outcome:
    """What happened on an earlier try of this same call."""
    model: str
    result: str


@dataclass(frozen=True)
class Decision:
    model: str | None  # None means a person takes it
    reason: str


def route(task: str, risk: str = "low", budget_left_usd: float = 1.0, prior: tuple[Outcome, ...] = ()) -> Decision:
    if task not in HAIKU_TASKS | SONNET_TASKS:
        raise ValueError(f"Unknown task class {task!r}")
    if risk not in RISKS:
        raise ValueError(f"Unknown risk {risk!r}")
    tried = {outcome.model for outcome in prior}
    if SONNET in tried:
        return Decision(None, "Sonnet already failed this call; a human takes it")
    escalate = any(outcome.result == SCHEMA_FAILURE or (outcome.result == LOW_CONFIDENCE and risk == "high")
                   for outcome in prior)
    wants_sonnet = task in SONNET_TASKS or escalate
    if not wants_sonnet:
        return Decision(HAIKU, f"{task} is high-volume work; Haiku is the default")
    if budget_left_usd < SONNET_CALL_ESTIMATE_USD:
        return Decision(None, f"Sonnet needed for {task} but ${budget_left_usd:.4f} is left on the case")
    why = f"{task} weighs options"
    if escalate:
        why = "after a failed Haiku try"
    return Decision(SONNET, f"Sonnet {why}")
