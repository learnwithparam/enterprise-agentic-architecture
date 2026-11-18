# ADR 0023: The coordinator only holds, and the supervisor settles overlaps by policy

Status: accepted, 29 October 2026.

## Context

Three teams plan contact with the same doctor. Marketing wants an email. A rep wants a visit. Medical has an open question. No one place sees all of it. So a doctor with an unanswered safety question could get a promotion the same week.

## Decision

`outreach.coordinate` reads HCP 360. It gives every planned touch one of two actions. One is `propose` (a human
may still approve it). The other is `hold`. It never sends. Each hold carries the rule that fired (`consent`,
`frequency_cap`, `open_medical_case`, `content_not_current`, `content_country`, `overlap`). It also carries the case or
touch behind it. `outreach.run` stores the decision on the touch. It writes each new hold to the ledger.
`supervisor.arbitrate` settles two proposals within three days of each other by policy. A
non-promotional touch beats a promotional one. Then the earlier date wins. No model arbitrates.
This follows the rule that an agent acts alone only in the risk-reducing direction.

## Consequences

- A hold can be explained from the ledger without replaying anything.
- The plan is served at `/api/hcps/{id}/outreach`, tenant scoped like every route.
- A freeze opened by the safety sentinel (P4.4) arrives as one more rule. It is not a new mechanism.
- Mutants cover the open-case rule, the arbitration order, overlap holds and the ledger write.
