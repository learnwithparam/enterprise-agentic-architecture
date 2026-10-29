# ADR 0024: The sentinel reads every channel, and insights name sources but never quote

Status: accepted, 29 October 2026.

## Context

A possible adverse event does not arrive only as a question to Medical Information. A rep writes it in a
CRM note, the call centre hears it, the portal chat mentions it. If only inquiries are screened, the
largest share of safety signals is never read.

## Decision

Every new interaction publishes `InteractionReceived` (keyed by its id, so a retry is one event). The
sentinel consumes that queue and screens each interaction with the deterministic safety screen, the same
floor the inquiry graph uses. A hit sends a `SafetySignal` to pharmacovigilance, writes a ledger entry
without the quoted words, and, when the sender resolves to a doctor, writes a contact freeze. A freeze
holds every planned touch for that doctor with the rule `safety_freeze`. The sentinel can freeze and can
never lift one: lifting needs a human. An unresolved sender still raises the signal and freezes nobody.

The insight agent reads resolved interactions and reports a theme only when at least two doctors raised
it. A digest lists source interaction ids and counts, never the words. It is for internal teams and is
never sent to a doctor.

## Consequences

- Safety recall no longer depends on which channel a note arrived by.
- The model screen is not run on interactions yet; the rule screen is the floor and the model may add hits
  later, never remove them. Adding it means a prompt version and a recording.
- A freeze has no automatic expiry. That is deliberate: a missed release is safer than a missed freeze.
- Mutants cover screening, freezing, the freeze rule, the announcement and the two-doctor threshold.
