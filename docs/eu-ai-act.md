---
title: EU AI Act classification
description: Where each agent falls under the EU AI Act, what duties follow, and which control in the platform meets each one
---

# EU AI Act classification

This is the engineering view for the design review, not legal advice. Legal confirms the classification
before a go-live in the EU.

## Where the platform sits

The platform is a system that answers doctors about approved product information, screens messages for
adverse events, plans outreach and summarises what doctors raise. It makes no decision about a patient's
care, a person's employment, credit, education or access to a public service, which are the Annex III
areas. A medical information assistant for healthcare professionals is therefore **not high-risk by
default**. Two features come close enough that the design keeps the high-risk evidence anyway, so a
reclassification costs paperwork and not a rebuild.

| Feature | Closest high-risk reading | Why it is limited-risk here | Evidence kept regardless |
|---|---|---|---|
| Safety sentinel screens messages for adverse events | A safety component that affects health | It only escalates to a qualified person and never closes or assesses a case | Recall of 1.0 on every release, quoted passages, the ledger |
| Outreach coordinator holds or proposes contacts | Profiling of people | The people are professionals, the signal is consent and contact history, and nothing is denied to them | Reason and rule per hold, source interactions |
| Insight agent clusters what doctors raise | Profiling | Output is for internal teams, names no doctor and quotes nobody | Two-doctor minimum, traced sources |

## Duties and the control that meets each

| Duty | Article | Control in the platform |
|---|---|---|
| Tell people they are dealing with an AI | 50 | An AI disclosure block is present in every assembled reply, checked before sending |
| Human oversight | 14 | The autonomy ladder, a reviewer for every non-cleared topic, a kill switch per country that Compliance holds |
| Record keeping | 12 | The hash-chained ledger, copied to S3 Object Lock for ten years, signed head |
| Accuracy and robustness | 15 | Id-only grounding, a verifier that runs again at the instant of sending, a red-team corpus, an eval gate per release |
| Risk management | 9 | The threat model in the architecture walkthrough, mutants that break each safety property |
| Data governance | 10 | Synthetic data in this repository, per-tenant row-level security, crypto-shredding for erasure |
| Technical documentation | 11 | The ADRs, the architecture walkthrough, the validation pack, the release manifest |
| General-purpose model obligations | 53 | Met by the model provider; the platform pins two model ids and records which release called which |

## What changes if a feature becomes high-risk

- The sentinel starts deciding whether a report is serious. That moves it into a medical-device-adjacent
  reading. Keep it escalate-only.
- The outreach coordinator starts to withhold information a doctor needs for patient care. Keep it a hold on
  promotion only.

Each of these is a roster row in `world/agents.toml` ("never" column) and a Cedar policy, so a change to
either is a reviewed diff and an ADR.
