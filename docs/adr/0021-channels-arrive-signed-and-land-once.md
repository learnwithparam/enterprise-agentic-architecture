# ADR 0021: Channels arrive signed and land once

Status: accepted, 29 October 2026.

## Context

The CRM, marketing, contact centre and portal each know something about the same doctor. The platform must hear all four. It must not trust a caller that merely knows the URL. It must not store a retried event twice. Some channels push as it happens. Others export a file at night.

## Decision

- **Webhook.** `POST /hooks/<tenant>/<channel>` takes no user token. The credential is an HMAC-SHA256 over
  `<timestamp>.<body>`. The secret is held per tenant and channel in SSM. A different body or secret is a 401.
  So is a timestamp more than five minutes off. A body that is not a record is a 422.
- **Batch.** A channel drops `*.jsonl` in S3 under `<tenant>/<channel>/incoming/`. A Temporal schedule
  starts `BatchImportWorkflow` for each tenant at 02:00 UTC, with overlap skipped. A file moves to
  `done/` after it is read. A bad line is counted. It is not fatal.
- **One door inside.** Both paths call `ingest.accept`. The row id is a hash of the channel and the
  sender's own event id. The insert ignores a conflict. So a retried webhook and a re-sent file are
  the same row. The table `interactions` is under row-level security per tenant.
- **Raw first.** A row keeps the sender's person id (`source_id`) and no `hcp_id`. Linking it to a
  person is identity resolution (P4.2).

## What a channel vouches for

A signed webhook proves the message came from that channel's backend. The sender id is that backend's claim. The platform did not check it. The reply always goes to the email on file for the matched doctor. It never goes to an address the sender supplied. A portal must verify the login before it sends an email as the source id.

## Consequences

- A leaked URL is useless without the secret. A captured request stops working after five minutes.
- Within the five minutes, a captured request could be sent again. But it lands as a duplicate.
- Rotating a secret is a new SSM value. A rotation workflow is not built.
- Events for consumers (sentinel, insight agent) are published when those agents arrive. So no queue
  collects messages nobody reads.
- Enforced by `tests/test_ingest.py` and five mutants in `scripts/mutate.py`.
