# ADR 0020: Delivery is at least once, so consumers are idempotent

Status: accepted, 29 October 2026.

## Context

SQS can deliver a message twice, a publisher can retry and send an event twice, and a handler can fail.
Before this change `events.drain` deleted a message before its handler ran, so a crash lost the event, and
nothing stopped a duplicate from running twice.

## Decision

- Every event carries `event_id` and `tenant`. `publish(..., key=)` lets a caller choose the id, so a
  retried publish is the same event.
- `events.consume(queue, handler)` runs the handler inside the event's tenant, and deletes the message
  only after the handler has finished. A table `processed_events` (row-level security per tenant) records
  `(tenant, event_id, queue)`, so a second delivery is deleted without running the handler again.
- A failure puts the message back at once. After `MAX_ATTEMPTS` (3) tries the event goes to `dead_letters`
  with its error and attempt count, and leaves the queue.
- `events.replay(id)` republishes a parked event under its own id and marks it replayed. It works once.
- Handlers must still be safe to repeat when they fail midway. `process_invalidations` is: eviction and
  re-verification give the same result the second time.

## Consequences

- A crashed steward no longer loses a withdrawal; the message is still on the queue.
- Operators can list and replay parked events. Their exposure as `/v1` routes and `hcp` commands comes
  with P5.4.
- API idempotency keys on write routes arrive with the webhooks (P4.1), where a retrying sender needs them.
- Enforced by `tests/test_events.py` and three mutants in `scripts/mutate.py`.
