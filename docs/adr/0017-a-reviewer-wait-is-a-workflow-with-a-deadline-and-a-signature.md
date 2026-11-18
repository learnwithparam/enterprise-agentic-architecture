# ADR 0017: A reviewer wait is a workflow with a deadline and a signature

Status: accepted, 29 October 2026.

## Context

A reviewer may take two days. A request cannot wait that long. A process that holds the wait loses it on a restart. Approving a reply is also a regulated act. You must be able to prove who approved it, and that it was them.

## Decision

- A case that ends `awaiting_review` starts a `ReviewWorkflow` (child of the inquiry, abandoned on parent
  close). The inquiry request returns at once. The review waits as long as it takes.
- A decision is a Temporal update. The activity runs `cases.approve` or `cases.reject`. So Cedar decides at
  the moment of the decision. A refusal is returned to the caller, and the wait goes on.
- The wait has a deadline (24 hours by default). At the deadline the workflow records `review_overdue` on
  the ledger and publishes `ReviewOverdue`. It does not send, drop or reassign anything. Escalation only
  makes the delay visible. That is the direction that reduces risk.
- Approval needs an electronic signature. The approver enters their password again, and Cognito checks it.
  The result (user, time, meaning, method) must be under five minutes old and name the approver. It is
  written to the ledger as `e_signature`. Rejecting needs no signature because it is the safe direction.
- A decision for a case with no waiting workflow is refused. So there is one path to a send.

## Consequences

The review workflow carries the approver's user record in its history. Production keeps the record to ids and roles. Starting a second review for a case with one open review reuses the open one. That one reads the case as it is now.

## Enforced by

`tests/test_durable.py` checks these. Approval sends only after the right reviewer signs. A missing, stale or someone else's signature is refused. An undecided review escalates once and stays open. A decision with no waiting workflow is refused. Four mutants in `scripts/mutate.py`.
