# ADR 0015: Sealed ledger data, and erasure by deleting a key

Status: accepted, 29 October 2026.

## Context

The ledger is append-only, hash-chained and archived under S3 Object Lock for ten years, so nothing in it
can be deleted. It also records what agents saw and said, and that includes quotes from a doctor's message.
GDPR Article 17 lets a person ask for their data to be erased. Both rules must hold.

## Decision

- Personal data goes into an entry only through `ledger.append(..., subject=, private=)`. It is written as
  a pseudonym plus AES-GCM ciphertext (`privacy.py`), under a key held in SSM for that one person.
- The hash covers the ciphertext. Deleting the key (`cases.erase_person`, Cedar action `ErasePerson`,
  compliance only) makes the text unreadable and leaves every hash, signature and archived object as it was.
  The erasure is itself a ledger entry that names the pseudonym and nobody else.
- The pseudonym is an HMAC under a per-tenant secret. It links one person's entries to each other and to
  nothing outside the tenant.
- Each tenant has its own chain, so one client's ledger is never read or verified with another's.
- Reads return entries sealed. Only the case view, behind `ViewCaseDetail`, opens them.

The safety sentinel keeps the rule from the roster: it acts alone only to reduce risk. Today it is the
safety agent plus the deterministic screen; it gains perception across channels in Act 3.

## Consequences

An erased person's entries still show that a call happened, its model, route and cost, which is the audit
trail. A key lost by accident erases the person the same way, so SSM keys are backed by the KMS-encrypted
parameter store and the production deploy adds per-tenant KMS keys.

## Enforced by

`tests/test_privacy.py`: output is absent from DynamoDB and the archive, reads stay sealed, erasure makes
data unreadable while `ledger.verify()` still passes, non-compliance users are refused and the refusal is
recorded, pseudonyms differ between people and tenants, and tenants have separate chains. Five mutants in
`scripts/mutate.py` remove each property.
