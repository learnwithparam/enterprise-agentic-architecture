# ADR 0008: A model router picks Haiku 5.5 or Sonnet 5.5 per call, then a human

Status: accepted, 29 October 2026.

## Context

Two models are allowed (ADR 0007). Which one answers a call should not be a constant in the code or the
caller's guess. Screening, classifying and selecting block ids are high-volume and narrow. Planning,
arbitrating between agents and writing insight digests weigh options. A malformed answer needs a second
try on a stronger model, and a second failure must not turn into a guess.

## Decision

`router.route(task, risk, budget_left_usd, prior)` is a pure function that returns a model or `None`, where
`None` means a human takes the call. The order is Haiku, then Sonnet, then a human.

- Screen, classify and select start on Haiku. Plan, arbitrate, synthesize and optimize start on Sonnet.
- A schema failure escalates to Sonnet once. Low confidence escalates only when the risk is high, which is
  the safety agent's case.
- A failure on Sonnet, or too little budget left for a Sonnet call, goes to a human. The router never
  falls back to a cheaper guess.
- `agents.call` runs the loop. An unrecoverable call raises `EscalateToHuman`, and `cases.run` turns that
  into a review route with nothing drafted, so a failure can only stop a send, never cause one.
- Each recording is keyed on the model that answered, cost is priced at that model's rate, and the audit
  entry carries the model and the router's reason.

## Options considered

- **A fixed model per agent.** Rejected: it cannot escalate, so a hard case either fails or every case
  pays for Sonnet.
- **The model chooses its own model.** Rejected: the choice affects cost and safety, so it belongs to
  reviewed code and not to model output.
- **Fall back to Haiku when the budget is low.** Rejected: a case that needed Sonnet and got a cheaper
  answer is a silent quality drop, so it goes to review.

## Consequences

Every router change is a release: the eval gate runs the router as a whole and compares Sonnet
escalation rate and cost per case with the baseline. The gateway (a later step) enforces budgets and
meters spend, and the router decides which model asks for them.

## Enforced by

`tests/test_router.py`: every task class lands on an allowed model, the starting model per class, one
escalation then a human, high-risk-only escalation on low confidence, no budget means a human, the call
loop tries Haiku then Sonnet then raises, pricing follows the answering model, and an escalated case is a
review with no draft. A mutant in `scripts/mutate.py` removes the human step and the suite must fail.
