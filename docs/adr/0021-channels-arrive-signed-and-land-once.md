# ADR 0021: Channels arrive signed and land once

Status: accepted, 29 October 2026.

## Context

The CRM, marketing, contact centre and portal each know something about the same doctor. The platform
must hear all four, without trusting a caller that merely knows the URL, and without storing a retried
event twice. Some channels push as it happens; others export a file at night.

## Decision

- **Webhook.** `POST /hooks/<tenant>/<channel>` takes no user token. The credential is an HMAC-SHA256 over
  `<timestamp>.<body>` with a secret held per tenant and channel in SSM. A body or secret that differs,
  or a timestamp more than five minutes off, is a 401. A body that is not a record is a 422.
- **Batch.** A channel drops `*.jsonl` in S3 under `<tenant>/<channel>/incoming/`. A Temporal schedule
  starts `BatchImportWorkflow` for each tenant at 02:00 UTC, with overlap skipped. A file moves to
  `done/` after it is read. A bad line is counted, not fatal.
- **One door inside.** Both paths call `ingest.accept`. The row id is a hash of the channel and the
  sender's own event id, and the insert ignores a conflict, so a retried webhook and a re-sent file are
  the same row. The table `interactions` is under row-level security per tenant.
- **Raw first.** A row keeps the sender's person id (`source_id`) and no `hcp_id`. Linking it to a
  person is identity resolution (P4.2).

## Consequences

- A leaked URL is useless without the secret, and a captured request stops working after five minutes.
- Within the five minutes a captured request could be sent again, but it lands as a duplicate.
- Rotating a secret is a new SSM value; a rotation workflow is not built.
- Events for consumers (sentinel, insight agent) are published when those agents arrive, so no queue
  collects messages nobody reads.
- Enforced by `tests/test_ingest.py` and five mutants in `scripts/mutate.py`.
