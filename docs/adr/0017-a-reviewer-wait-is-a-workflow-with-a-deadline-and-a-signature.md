# ADR 0017: A reviewer wait is a workflow with a deadline and a signature

Status: accepted, 29 October 2026.

## Context

A reviewer may take two days. A request cannot wait that long, and a process that holds the wait loses it
on a restart. Approving a reply is also a regulated act: who approved, and that it was them, must be provable.

## Decision

- A case that ends `awaiting_review` starts a `ReviewWorkflow` (child of the inquiry, abandoned on parent
  close). The inquiry request returns at once; the review waits as long as it takes.
- A decision is a Temporal update. The activity runs `cases.approve` or `cases.reject`, so Cedar decides at
  the moment of the decision. A refusal is returned to the caller and the wait goes on.
- The wait has a deadline (24 hours by default). At the deadline the workflow records `review_overdue` on
  the ledger and publishes `ReviewOverdue`. It does not send, drop or reassign anything: escalation only
  makes the delay visible, which is the risk-reducing direction.
- Approval needs an electronic signature: the approver enters their password again, Cognito checks it, and
  the result (user, time, meaning, method) must be under five minutes old and name the approver. It is
  written to the ledger as `e_signature`. Rejecting needs no signature because it is the safe direction.
- A decision for a case with no waiting workflow is refused, so there is one path to a send.

## Consequences

The review workflow carries the approver's user record in its history; production keeps the record to ids
and roles. Starting a second review for a case with one open reuses the open one, which reads the case as
it is now.

## Enforced by

`tests/test_durable.py`: approval sends only after the right reviewer signs, a missing, stale or someone
else's signature is refused, an undecided review escalates once and stays open, and a decision with no
waiting workflow is refused. Four mutants in `scripts/mutate.py`.
