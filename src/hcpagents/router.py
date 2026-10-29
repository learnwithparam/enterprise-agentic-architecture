"""The model router: which of the two allowed models answers this call, or whether a human does.

Inputs are the task class, the risk, the budget left on the case and the outcome of earlier tries.
The order is Haiku, then Sonnet, then a human. It never returns a model outside ALLOWED_MODELS,
and it is a pure function so the eval gate can run it as a whole (ADR 0008).
"""

from dataclasses import dataclass

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"

# High-volume, narrow work stays on Haiku. Open-ended work that weighs options goes to Sonnet.
HAIKU_TASKS = frozenset({"screen", "classify", "select"})
SONNET_TASKS = frozenset({"plan", "arbitrate", "synthesize", "optimize"})
RISKS = ("low", "high")
SONNET_CALL_ESTIMATE_USD = 0.01  # what one Sonnet call may cost; below this budget we ask a human instead

SCHEMA_FAILURE = "schema_failure"
LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class Outcome:
    """What happened on an earlier try of this same call."""
    model: str
    result: str


@dataclass(frozen=True)
class Decision:
    model: str | None  # None means a human takes it
    reason: str


def route(task: str, risk: str = "low", budget_left_usd: float = 1.0, prior: tuple[Outcome, ...] = ()) -> Decision:
    if task not in HAIKU_TASKS | SONNET_TASKS:
        raise ValueError(f"Unknown task class {task!r}")
    if risk not in RISKS:
        raise ValueError(f"Unknown risk {risk!r}")
    tried = {o.model for o in prior}
    if SONNET in tried:
        return Decision(None, "Sonnet already failed this call; a human takes it")
    escalate = any(o.result == SCHEMA_FAILURE or (o.result == LOW_CONFIDENCE and risk == "high") for o in prior)
    wants_sonnet = task in SONNET_TASKS or escalate
    if not wants_sonnet:
        return Decision(HAIKU, f"{task} is high-volume work; Haiku is the default")
    if budget_left_usd < SONNET_CALL_ESTIMATE_USD:
        return Decision(None, f"Sonnet needed for {task} but ${budget_left_usd:.4f} is left on the case")
    why = "after a failed Haiku try" if escalate else f"{task} weighs options"
    return Decision(SONNET, f"Sonnet {why}")
