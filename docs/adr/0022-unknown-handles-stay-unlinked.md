# ADR 0022: A channel's id resolves to one doctor or to nobody

Status: accepted, 29 October 2026.

## Context

The four channels know a doctor by different handles. They are a CRM id, a marketing id, a phone number and a portal email. HCP 360 is the agents' shared memory. So a wrong link is worse than a missing one. Say the wrong doctor mentions a rash. That opens a safety case on the wrong person. It also hides the right one.

## Decision

`identity.resolve(channel, source_id)` looks the handle up in the current tenant's HCP list. It compares
phones by digits and emails by lower case. The national registry id works on any channel. A handle may match
no doctor, or more than one. Then it resolves to nothing, and the interaction keeps an empty `hcp_id`.
`identity.unresolved()` lists those for a human. `identity.link_pending()` links earlier interactions
once a handle becomes known. Resolution happens inside the insert in `ingest.accept`. So a row is never
visible half-linked. Matching is exact on purpose. There are no fuzzy names.

## Consequences

- Another tenant's handle never matches. The lookup reads only the current tenant's list.
- An ambiguous handle waits for a human instead of being guessed.
- The 360 view now carries `interactions`, the raw words of every channel. Agents read them from there.
- Mutants cover digit matching, the ambiguity guard, the registry id, linking on arrival and late linking.
