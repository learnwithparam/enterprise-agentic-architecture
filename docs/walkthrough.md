---
title: Walkthrough
description: Start here. The problem a medical information team has, what the platform does about it, and how to run and break it
---

# Walkthrough

## The problem

A doctor asks a drugs company a question. Can this medicine be used in pregnancy? What is the dose for a child? Is it safe with another drug? Three things can go wrong. Each one is a regulatory event.

- **A wrong or invented answer.** A sentence nobody approved reaches a doctor.
- **A missed safety report.** The question mentions a side effect, and nobody files it with pharmacovigilance.
- **A leak.** One client's content, or one doctor's history, shows up in another client's reply.

An agent that writes the reply makes all three easy. So the platform never lets a model write what a doctor reads. The model picks approved content blocks and states facts. A table of rules decides where the case goes. Code checks every sentence against a block.

## What you build

This is a platform for many clients. It answers doctors' inquiries. It sends every case to one of six places.

| Route | Meaning |
|---|---|
| `send` | Cleared for an automatic reply |
| `review` | A medical reviewer reads the draft first |
| `offlabel` | The question is outside the approved use |
| `pv` | A possible side effect goes to pharmacovigilance |
| `decline` | Nothing can be said |
| `specialist` | A person with the right expertise takes it |

Around that sit a policy kernel and a model router. There is also an audit ledger that cannot be rewritten. Reviewers get a console. An eval gate decides whether a new prompt may ship. The first tenant is Quillon Biopharma. The second is Marlowe Therapeutics.

## How it works

One inquiry passes three small agents. Then code decides.

```mermaid
flowchart LR
  q(["Inquiry"]) --> safety["Safety agent<br/>side effect mentioned?"]
  safety --> triage["Triage agent<br/>product, country, topics"]
  triage --> assembler["Assembler agent<br/>picks approved block ids"]
  assembler --> ground["Grounding check<br/>every sentence traced to a block"]
  ground --> rules{"Routing table<br/>safety rows first"}
  rules -->|cleared| send["send"]
  rules -->|any doubt| review["review"]
  rules -->|side effect| pv["pv"]
  rules -->|outside label| other["offlabel, decline, specialist"]
```

Something that is not a model limits every step.

```mermaid
sequenceDiagram
  participant D as Doctor
  participant A as Agents
  participant K as Policy kernel
  participant DB as Postgres (row-level security)
  participant L as Ledger
  D->>A: inquiry
  A->>K: may this agent call this tool for this tenant?
  K-->>A: allow or deny, with the reason
  A->>DB: search approved blocks (only this tenant's rows)
  DB-->>A: blocks
  A->>L: append what was decided and why
  A-->>D: reply, or a reviewer's approved draft
```

- **Tenants are separated by the database.** Every table forces row-level security on a tenant id, and a test walks every table to prove it.
- **A long wait is a workflow.** A case waiting for a reviewer is a Temporal workflow that survives a restart.
- **Rules only tighten.** A guardian agent can switch a country's automatic replies off when reviewers reject too many drafts. Only a person can switch them on.
- **A prompt change is a release.** The eval gate scores every inquiry on the new prompt and refuses the release if routing, grounding or safety gets worse.

Read [the architecture walkthrough](./architecture-walkthrough.md) for the full tour. It follows one doctor at a time.

## Run it

Replay needs no key. Every model answer is a committed recording.

```bash
make up          # Floci (local AWS), Postgres, Temporal and Valkey, then every resource
make check       # tests, evals, mutants, prose, web build, mermaid, CSP
make serve       # console on http://localhost:8765
```

Expect `make check` to end with no failures. The console lists the twenty inquiries with their routes. To record again, you need an `ANTHROPIC_API_KEY`.

```bash
make record      # calls claude-haiku-5-5 for every inquiry, about two cents
```

Recording rewrites `evidence/live.json`. A test compares it with the request each inquiry would make now. So an edit to a prompt names the inquiries it changed.

## What to watch for

- **Replay hides nothing, but it proves only what was recorded.** After a prompt change, run `make record` or the freshness test names the stale inquiries.
- **Operator detail stays inside.** Model names, spend and stack traces never reach a doctor.
- **Floci is an emulator.** It stubs the Bedrock reply and has no device-code sign-in, so the CLI signs in with a browser and PKCE. [Floci support](./floci-support.md) lists every limit that remains.
- **Fail closed.** When anything is unclear the case goes to `review`, never to `send`.
- **Break one rule on purpose.** Remove a row-level security policy or a routing row and watch the named test fail; that is how you learn which test guards which rule.

## Where to go next

Fourteen labs each teach one idea with a test you can break. Start with these three.

- [route inquiries with a routing table](../labs/route-inquiries-with-a-routing-table/README.md)
- [isolate tenants with row-level security](../labs/isolate-tenants-with-row-level-security/README.md)
- [ground replies with approved blocks](../labs/ground-replies-with-approved-blocks/README.md)

The full list is in the [lab index](../labs/README.md). The decisions are in `docs/adr/`. [The case study](./case-study.md) says what was built, what was left out and why.
