# ADR 0022: A channel's id resolves to one doctor or to nobody

Status: accepted, 29 October 2026.

## Context

The four channels know a doctor by different handles: a CRM id, a marketing id, a phone number, a portal
email. HCP 360 is the agents' shared memory, so a wrong link is worse than a missing one. A rash mentioned
by the wrong doctor opens a safety case on the wrong person and hides the right one.

## Decision

`identity.resolve(channel, source_id)` looks the handle up in the current tenant's HCP list, comparing
phones by digits and emails by lower case. The national registry id works on any channel. A handle that
matches no doctor, or more than one, resolves to nothing and the interaction keeps an empty `hcp_id`.
`identity.unresolved()` lists those for a human. `identity.link_pending()` links earlier interactions
once a handle becomes known. Resolution happens inside the insert in `ingest.accept`, so a row is never
visible half-linked. Matching is exact on purpose: no fuzzy names.

## Consequences

- Another tenant's handle never matches, because the lookup reads only the current tenant's list.
- An ambiguous handle waits for a human instead of being guessed.
- The 360 view now carries `interactions`, the raw words of every channel. Agents read them from there.
- Mutants cover digit matching, the ambiguity guard, the registry id, linking on arrival and late linking.
