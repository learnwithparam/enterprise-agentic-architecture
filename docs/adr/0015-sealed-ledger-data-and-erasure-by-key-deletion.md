# ADR 0015: Sealed ledger data, and erasure by deleting a key

Status: accepted, 29 October 2026.

## Context

The ledger is append-only, hash-chained and archived under S3 Object Lock for ten years. So nothing in it can be deleted. It also records what agents saw and said. That includes quotes from a doctor's message. GDPR Article 17 lets a person ask for their data to be erased. Both rules must hold.

## Decision

- Personal data goes into an entry only through `ledger.append(..., subject=, private=)`. It is written as
  a pseudonym plus AES-GCM ciphertext (`privacy.py`). The key is held in SSM for that one person.
- The hash covers the ciphertext. Deleting the key (`cases.erase_person`, Cedar action `ErasePerson`,
  compliance only) makes the text unreadable. Every hash, signature and archived object stays as it was.
  The erasure is itself a ledger entry. It names the pseudonym and nobody else.
- The pseudonym is an HMAC under a per-tenant secret. It links one person's entries to each other. It links
  them to nothing outside the tenant.
- Each tenant has its own chain. So one client's ledger is never read or checked with another's.
- Reads return entries sealed. Only the case view, behind `ViewCaseDetail`, opens them.

The safety sentinel keeps the rule from the roster. It acts alone only to reduce risk. Today it is the
safety agent plus the deterministic screen. It gains perception across channels in Act 3.

## Consequences

An erased person's entries still show that a call happened. They show its model, route and cost. That is the audit trail. A key lost by accident erases the person the same way. So SSM keys are backed by the KMS-encrypted parameter store. The production deploy adds per-tenant KMS keys.

## Enforced by

`tests/test_privacy.py` checks these. The output is absent from DynamoDB and the archive. Reads stay sealed. Erasure makes data unreadable while `ledger.verify()` still passes. Users outside compliance are refused, and the refusal is recorded. Pseudonyms differ between people and tenants. Tenants have separate chains. Five mutants in `scripts/mutate.py` remove each property.
