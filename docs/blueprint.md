---
title: System blueprint
description: One picture of the whole system. The data flow, the data firewall, the approval path, the AWS layout and every place a human decides
---

# System blueprint

This page is the picture of the whole system in one place. The [architecture walkthrough](./architecture-walkthrough.md) follows one doctor through the code, one small diagram at a time. This page shows all of it at once.

Four of the tables below are read by `tests/test_blueprint.py`. If the code changes and the table does not, the test fails.

## 1. Data flow

Four channels bring a doctor's message in. One identity resolves the doctor. A rule floor looks for a safety signal before any model reads the text. Then the case takes one of six routes.

```mermaid
flowchart LR
    CRM[CRM] --> IN
    MKT[Marketing] --> IN
    CC[Contact centre] --> IN
    BOT[Chatbot and portal] --> IN
    IN[Signed webhook or batch] --> ID[Identity: one doctor]
    ID --> RULES[Safety rule floor]
    RULES -->|signal| FORK[Safety intake, own workflow]
    RULES --> CASE[Case workflow]
    CASE --> TOK[Vault: names become tokens]
    TOK --> MODEL[Model reads tokens only]
    MODEL --> GROUND[Every sentence matched to an approved block]
    GROUND --> ROUTE{Route}
    ROUTE -->|safe| SEND[Send after a last check]
    ROUTE -->|needs a person| REVIEW[Reviewer queue]
    ROUTE -->|safety| PV[Safety team]
    ROUTE -->|off label| MED[Medical team]
    ROUTE -->|specialist| SPEC[Specialist]
    ROUTE -->|decline| STOP[Decline]
    REVIEW -->|signed approval| SEND
    SEND --> LEDGER[(Hash chained ledger)]
```

**Legend.** A box is a step. A rounded edge label is the condition. The safety intake runs in its own workflow, so the case never waits for it. The ledger takes every decision, and each entry holds the hash of the one before it.

## 2. Data firewall

Medical, safety and commercial data live in separate database schemas. Each has its own login. The commercial login has no privilege on the other two. The only thing that crosses is a hold: a doctor, a product and a reason, with no case id and no text. The database writes the hold itself.

```mermaid
flowchart TB
    subgraph MZ[Medical zone, login hcp_medical]
        CASES[(Cases and reviews)]
    end
    subgraph SZ[Safety zone, login hcp_safety]
        INTAKE[(Intakes and freezes)]
    end
    subgraph CZ[Commercial zone, login hcp_commercial]
        TOUCH[(Doctors and touches)]
    end
    subgraph SH[Shared]
        HOLD[(Contact hold)]
    end
    CASES -->|database trigger| HOLD
    INTAKE -->|database trigger| HOLD
    HOLD --> TOUCH
    CZ -.->|no privilege| MZ
    CZ -.->|no privilege| SZ
```

**Legend.** A solid arrow is the only way data crosses. A dotted arrow is a refusal by the database. Each zone has its own KMS key in the stack.

Who gets which view of a doctor. Cedar decides it, in `policies/cedar/zones.cedar`.

| Role | View | What it holds |
|---|---|---|
| medical_reviewer | medical | Cases, notes and counts |
| pv | medical | Cases, notes and counts |
| compliance | medical | Cases, notes and counts |
| mi_specialist | commercial | Profile and holds only |
| content_owner | commercial | Profile and holds only |
| field_rep | commercial | Profile and holds only |

What may be said to whom. Each content block carries a type and an audience. The search filters on the audience before it ranks anything.

| Block type | Doctor | Rep | Chatbot |
|---|---|---|---|
| PI | yes | yes | no |
| SRD | yes | no | no |
| SELF_SERVICE | no | no | yes |
| TEMPLATE | yes | yes | yes |

PI is the product information. SRD is a standard response document, for example on renal impairment, pregnancy or interactions.

## 3. Approval path

A signature covers one exact reply. The reviewer signs in again. The system makes a digest of the text, each block and its version, the doctor, the country, the release and the draft version. The ledger key signs the digest. The send makes the digest again and stops if anything moved.

```mermaid
sequenceDiagram
    participant R as Reviewer
    participant A as Approval
    participant K as Ledger key
    participant S as Send
    participant L as Ledger
    R->>A: Sign in again and approve
    A->>A: Digest of reply, blocks, doctor, release, version
    A->>K: Sign the digest
    K-->>A: Signature
    A->>S: Send
    S->>S: Digest again, check every block is still approved
    S-->>L: Sent with digest, or Send blocked with reasons
```

**Legend.** Time runs down. A withdrawal of a block closes every draft that uses it at once, before anyone can sign it.

## 4. AWS layout

This build separates the zones inside one database cluster, with one KMS key per zone. In production each zone is its own AWS account.

```mermaid
flowchart LR
    subgraph ORG[AWS organisation]
        subgraph A1[Medical account]
            M1[(Aurora medical)]
            K1[KMS key]
        end
        subgraph A2[Safety account]
            M2[(Aurora safety)]
            K2[KMS key]
        end
        subgraph A3[Commercial account]
            M3[(Aurora commercial)]
            K3[KMS key]
        end
        subgraph A4[Audit account]
            S3[(S3 Object Lock)]
        end
    end
    A1 -->|hold event| A3
    A2 -->|hold event| A3
    A1 --> S3
    A2 --> S3
    A3 --> S3
```

**Legend.** Each box is one account. Only the hold event crosses between zones. Every account writes to the audit bucket, which cannot be changed. We only run `cdk synth` for this layout. We have not deployed separate accounts.

## 5. Every place a human decides

| Decision | Role | Code |
|---|---|---|
| Approve a reply to a doctor | medical_reviewer | `case_review.py::approve` |
| Reject a reply to a doctor | medical_reviewer | `case_review.py::reject` |
| Approve a planned email | field_rep | `outreach.py::approve` |
| Acknowledge a safety intake | pv | `safety_clock.py::acknowledge` |
| Screen an event by hand while the detector is down | pv | `safety_clock.py::send_to_manual_screening` |
| Withdraw a content block | content_owner | `case_review.py::withdraw` |
| Turn automatic replies on or off for a country | compliance | `case_review.py::set_autonomy` |
| Make a release the baseline | compliance | `releases.py::promote` |

## What this build does not do

- It does not run separate AWS accounts. It synthesises the stack only.
- The business day clock for the safety acknowledgment skips weekends. It has no holiday calendar.
- Name detection by the model works in English text only. German names rely on the names list and the title pattern.
