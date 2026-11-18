# ADR 0005: A hash-chained ledger archived under S3 Object Lock

Status: accepted, 15 October 2026

## Context

Compliance must show an inspector what happened on any case. They must also trust that nobody changed it later. That includes the team that runs the platform. A table with an audit column proves nothing to a person who does not trust the database admins.

## Decision

Every event is added to a ledger (`hcpagents.ledger`). Each entry carries the SHA-256 of itself and
the hash of the entry before it. Each entry is also copied to an S3 bucket. The bucket uses Object Lock in compliance mode for ten
years. Every tenth entry, the head of the chain is signed with an asymmetric KMS key. `verify()` walks the chain. It
names the first entry that no longer matches.

## Options considered

- **CloudTrail alone.** Rejected: records API calls, not business decisions.
- **Amazon QLDB.** Rejected: AWS has ended it.
- **Hash chain plus Object Lock plus KMS signing.** Chosen. Each piece is a standard service Compliance can
  check with its own tools.

## Consequences

If someone edits a past entry, the check finds it at that entry. You can restore it from the archive. A reset starts a new chain. Locked objects from old chains stay.

## Enforced by

`tests/test_flow.py::test_ledger_detects_tampering_and_the_archive_refuses_deletion` and `test_every_tool_call_is_on_the_ledger_with_its_guard_decision`.
