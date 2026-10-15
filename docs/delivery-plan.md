---
title: Delivery plan
description: How the case study is delivered as real work, from the first conversation with the client to the readout, with what each stage produces and the evidence that closes it
---

# Delivery plan

The case study is the first three weeks of a real engagement, compressed. Each stage ends with an artifact
in this repository and a named person who has to agree with it. A stage is closed by evidence, not by a
date; the days are a plan, and the plan moves when the evidence says so.

| Stage | Days | Closes when | Artifact |
|---|---|---|---|
| Listen | 1 to 2 | The client confirms the problem statement in their own words | `docs/case-study.md` Part A section 1 |
| Test the riskiest assumptions | 3 to 5 | Each assumption has a result or an owner and a date | Assumption log in Part A section 1 |
| Decide the architecture | 4 to 6 | Each ADR is accepted by the architect and Compliance | `docs/adr/` |
| Build the slice | 6 to 12 | `make check` is green and the mutation run kills every mutant | The code, `make check` |
| Review with Compliance and Medical | 13 to 14 | Every refusal is walked through and signed off | `docs/product-walkthrough.md` |
| Read out | 15 | The steering group chooses the first release scope | Part A section 5, this plan |

## Listen, days 1 to 2

**Who:** the head of medical information, a German medical reviewer, the pharmacovigilance intake lead,
a brand lead, the CRM owner, a compliance officer and the platform team on AWS.

**Ask each of them:** what happened the last time a question went wrong, what they would need to see before
trusting a reply that no human read, and which number they are judged on.

**Produce:** the problem statement in Part A section 1, written so each of them recognises their own words,
and the six riskiest assumptions ranked by how much of the design falls over if each one is false.

**The trap to avoid:** designing the agent before knowing whether approved content exists as reusable
blocks. If it does not, the first release is a content project, and the plan says so on day two.

## Test the riskiest assumptions, days 3 to 5

Each assumption gets the cheapest test that could prove it false.

| Assumption | Test | Pass looks like |
|---|---|---|
| Approved content exists as blocks with approval ids | Export the current German Veltrona standard responses from the content system | Each paragraph has an id, a version and an approval reference |
| Medical accepts replies built from verbatim blocks | Show three composed replies to two reviewers next to the replies they sent last month | Both would send them unchanged, or name the change |
| The adverse event screen reaches full recall | Run the screen over 200 past inquiries pharmacovigilance has already coded | No coded event is missed; false positives are counted, not hidden |
| One doctor can be matched across systems | Match 500 CRM records to the contact centre and portal on registry id | The unmatched rate is known, with the reasons |
| Country rules can be written as data | Write the German label scope, promotional cap and disclosure as TOML with a reviewer | The reviewer reads it and agrees it is the rule |
| Claude runs where the data must stay | Check Bedrock availability for Haiku 5.5 in the EU regions with the platform team | A region and an inference profile are named |

A failed test changes the plan the same day. The slice in this repository assumes every test passed and
uses synthetic data shaped like what each test should find.

## Decide the architecture, days 4 to 6

Write one ADR per decision that would be expensive to reverse, with the options considered and the failure
each one prevents. The seven in `docs/adr/` are the decisions for this slice. Each names the test that
enforces it, so the decision cannot quietly drift once the code exists.

Review them with the architect who owns the AWS landing zone and with Compliance in one session, because the
two groups reject different things: the architect rejects new moving parts, Compliance rejects anything it
cannot audit.

## Build the slice, days 6 to 12

Build in the order that makes the riskiest part real first.

1. **The routing table and its tests.** Safety rules first. Nothing else is worth building if an adverse
   event can reach a send.
2. **The content store and grounding check.** A reply that is not traced sentence by sentence to current
   approved content is never sent, so this check exists before any agent does.
3. **The three agents, in replay.** Record each agent once on Haiku 5.5, then build everything else against
   the recordings so the build costs nothing and gives the same result every time.
4. **Guards, Cedar and the ledger.** Every tool call and every human action goes through a policy and lands
   on the hash chain.
5. **Handoffs, HCP 360 and the console.** The parts people see last, because they change most once people
   see them.
6. **The eval gate.** Twenty inquiries with expected routes, one missed adverse event fails the release.

**Mutation run, day 12.** Break each safety property in the code one at a time (drop a routing rule, skip
the send time check, let another country's block through, accept another model id) and confirm a test fails
for every one. A mutant that survives is a missing test, and the slice is not done until it is written.

## Review with Compliance and Medical, days 13 to 14

Walk the product walkthrough screen by screen, with the refusals first: the adverse event that is not
answered, the off-label question, the injection, the field rep who cannot read a case, the withdrawn block
that blocks an approved send, the reviewer from the wrong country, the tampered ledger. Each refusal is a
sign-off line with a name next to it.

Medical reviews every content block the slice uses and every reply the eval set produces. Pharmacovigilance
confirms the fields the safety event carries are the fields their intake needs.

## Read out, day 15

Forty minutes with the steering group.

1. The problem in their words, and what the assumption tests found (five minutes).
2. The slice, live, refusals first (fifteen minutes).
3. The architecture on one page and the ADRs that need their decision (ten minutes).
4. The first release scope and the success measures from Part A section 5 (five minutes).
5. The open questions only they can answer (five minutes).

The readout ends with one decision: which country, product and channels go first, and who in that country
can clear a topic for automatic replies.

## After the readout

| Weeks | Work |
|---|---|
| 1 to 4 | Germany, Veltrona, portal and email. Every draft approved by a human. Capture the baselines. |
| 5 to 8 | Compliance clears dosing, then administration, then storage, each after its approval rate holds above 90%. |
| 9 to 12 | The second country, by adding its label scope, cap, disclosure and reviewers as data and its Cedar entities. |

No week in this table adds a model, a channel and a country at once. Each change ships alone, through the
gate, so a regression has one cause.
