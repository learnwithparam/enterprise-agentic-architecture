# ADR 0005: A hash-chained ledger archived under S3 Object Lock

Status: accepted, 15 October 2026

## Context

Compliance must be able to show an inspector what happened on any case, and trust that nobody changed
it afterwards, including the team that runs the platform. A database table with an audit column proves
nothing to someone who does not trust the database's administrators.

## Decision

Every event is appended to a ledger (`hcpagents.ledger`). Each entry carries the SHA-256 of itself and
the previous entry's hash. Each entry is copied to an S3 bucket under Object Lock in compliance mode for ten
years. Every tenth entry the chain head is signed with an asymmetric KMS key. `verify()` walks the chain and
names the first entry that no longer matches.

## Options considered

- **CloudTrail alone.** Rejected: records API calls, not business decisions.
- **Amazon QLDB.** Rejected: AWS has ended it.
- **Hash chain plus Object Lock plus KMS signing.** Chosen. Each piece is a standard service Compliance can
  verify with its own tools.

## Consequences

An edit to a past entry is detected at that entry and can be restored from the archive. A reset starts
a new chain; locked objects from old chains stay.

## Enforced by

`tests/test_flow.py::test_ledger_detects_tampering_and_the_archive_refuses_deletion` and
`test_every_tool_call_is_on_the_ledger_with_its_guard_decision`.
