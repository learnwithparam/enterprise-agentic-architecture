---
title: Product walkthrough
description: What the medical information console is, the problem it solves, and a screen-by-screen script for demoing it to Compliance, Medical and engineering leadership
---

# Product walkthrough

Quillon MI is the console for one narrow slice of a regulated HCP engagement platform: answering
unsolicited medical questions from doctors. Quillon Biopharma, its products Veltrona and Ombrexa, every
doctor and every sentence of content are synthetic.

## The problem

A doctor asks a product question through the portal, by email, through the contact centre, the chatbot or
a field rep. Today the question waits days while Medical, Legal and Regulatory pass it around, and the reply
that finally goes out cannot be traced to the approved version of the text it quotes. Nobody can say
whether that text was still approved on the day it was sent.

Two failures matter more than speed. A message that mentions a side effect is an adverse event report with
a legal reporting clock, and it must reach pharmacovigilance whatever channel it came from. A question
outside the approved label must never get a promotional answer. A model that writes fluent medical text
fails both tests, because nobody can prove what it will say next time.

## How the console solves it

The AI never writes a sentence a doctor reads. Three small agents on Claude Haiku 5.5 read the message,
split it into questions and pick ids of approved content blocks. Plain code places those blocks verbatim
between fixed templates, checks every sentence against the content store as it is today, and walks a fixed
routing table to decide where the case goes. Only an on-label question, fully covered by current content,
on a topic Compliance has cleared for that country, is sent without a human. Everything else goes to the
team that owns it, with the reason written down.

Every decision lands in a hash-chained ledger archived under S3 Object Lock, every permission comes from
Cedar policies in Verified Permissions, and every change ships only through an eval gate that fails on one
missed adverse event.

## Before you record

- **Start the stack:** `make up` starts Floci, the local AWS emulator, and provisions every resource.
- **Reset state:** `make provision` wipes cases and the ledger and reseeds the world.
- **Serve the console:** `make serve`, then open `http://localhost:8765`. The persona menu at the top right
  switches who you are; every permission follows from that choice.
- **Refresh the captures:** `make walkthrough`. It needs `cwebp` and port 8765 free. It reprovisions, runs
  every inbox inquiry in replay, captures every screen below as `<screen>-desktop.webp` in
  `docs/product-walkthrough-shots/` and runs the test that keeps this page and the shots in step.
  `WALKTHROUGH_SCREENS=proof,kill-switch make walkthrough` recaptures only those.

Nothing in this walkthrough calls the model. Replay runs the recorded agent calls through the same guards,
so a demo costs nothing and gives the same result every time.

## Recording order

1. The architecture and the routing table.
2. The inbox and five cases, one per route.
3. The review bench and HCP 360.
4. The moments the platform says no to a human.
5. The proof Compliance checks.

## 1. How it is built

### Architecture

**Go to** `/`. **Show** the headline "Every reply traced to approved content, or no reply at all." and the
seven graph nodes. Three are outlined in purple and marked "Uses the model"; four are "Plain code".

**Say:** "Seven steps run in order. Only three touch the model, and none of those three can choose where a
case goes or write a word the doctor reads."

![Architecture](./product-walkthrough-shots/architecture-desktop.webp)

### Routing table

**Go to** the routing table on the same page. **Show** the ten rules, safety first, ending in "Every rule
passed: Sent automatically".

**Say:** "Order is the policy. An adverse event wins over everything. The same table generates the Step
Functions definition, and tests check the safety rules hold for every combination of facts."

![Routing table](./product-walkthrough-shots/routing-table-desktop.webp)

## 2. Five cases, five routes

### Inbox

**Go to** `/inbox`. **Show** twelve questions from five channels, each with where it went: sent
automatically, medical review, off-label, pharmacovigilance, declined.

**Say:** "Same platform, five different outcomes, and every one of them is a rule you can read."

![Inbox](./product-walkthrough-shots/inbox-desktop.webp)

### A reply sent without a human

**Go to** `/case?id=inq-101`. **Show** the trace on the left and the reply on the right. Every sentence has a
margin with its block id, version and MLR approval number, and the header reads "10 sentences, 10 traced".

**Say:** "Dr. Kaya asked about dosing and food. Both topics are cleared for automatic replies in Germany, so
this went out in under a second. Point at any sentence and you see the approval it came from."

![Case sent](./product-walkthrough-shots/case-sent-desktop.webp)

### A draft that waits for a reviewer

**Go to** `/case?id=inq-103`. **Show** Rule 10 matched: renal impairment is covered by approved content but
not cleared for automatic replies in Germany, and the yellow box where a German reviewer approves or rejects.

**Say:** "Covered is not the same as cleared. Compliance decides which topics go out alone, per country."

![Case review](./product-walkthrough-shots/case-review-desktop.webp)

### An adverse event

**Go to** `/case?id=inq-105`. **Show** the "Not answered" stamp, the three quoted signals (two found by
keyword rules, one by the safety agent) and the trace stopping after the safety screen.

**Say:** "A rash and a fever after starting the drug. The graph stops here. Pharmacovigilance owns it, the AI
drafts nothing, and the quoted words go to their intake queue."

![Case adverse event](./product-walkthrough-shots/case-adverse-event-desktop.webp)

### An attempt to change the rules

**Go to** `/case?id=inq-107`. **Show** the injection rule matching the words "Ignore all previous
instructions" and the case declined with nothing drafted.

**Say:** "The message is data, never instructions. A keyword rule catches the attempt beside the triage
agent, and either one is enough to decline."

![Case injection](./product-walkthrough-shots/case-injection-desktop.webp)

### An off-label question

**Go to** `/case?id=inq-104`. **Show** the scope check: a 14 year old is outside the German label, so the case
goes to Medical and the AI drafts nothing.

**Say:** "The same question is on-label in one country and off-label in another. The label is checked per
country, in code."

![Case off-label](./product-walkthrough-shots/case-off-label-desktop.webp)

### Agent calls and guards

**Go to** the bottom of `/case?id=inq-101`. **Show** each agent's tokens and cost, and every tool call the
assembler made with the Cedar decision "Verified Permissions: ALLOW (agents.cedar)".

**Say:** "Each agent call costs a fraction of a cent on Haiku 5.5. Every tool call goes through a guard and
the policy store before it runs, and both decisions are on the ledger."

![Case guards](./product-walkthrough-shots/case-guards-desktop.webp)

## 3. Where humans work

### Review bench

**Go to** `/review`. **Show** the queues grouped by owner: drafts awaiting a medical reviewer, cases with
pharmacovigilance, off-label cases with Medical, declined.

**Say:** "Everything the AI did not finish, grouped by who owns it. Only the first queue holds AI drafts."

![Review bench](./product-walkthrough-shots/review-bench-desktop.webp)

### HCP 360

**Go to** `/hcp?id=hcp-kaya`. **Show** one doctor joined across CRM, marketing, contact centre and portal, the
timeline, and the planned marketing email held because Germany's cap is two promotional touches in 30
days.

**Say:** "This is where overlapping messages stop. Every planned touch is checked against consent, the
country cap, open medical cases and whether its content is still current."

![HCP 360](./product-walkthrough-shots/hcp-360-desktop.webp)

## 4. When the platform says no to a human

### A field rep cannot read case detail

**Switch persona** to Tom Becker, field representative. **Go to** `/case?id=inq-105`. **Show** that the
case detail is refused.

**Say:** "Reps see that a case exists and its status, never the medical detail. That is one Cedar policy,
not a check buried in the code."

![Field rep denied](./product-walkthrough-shots/field-rep-denied-desktop.webp)

### Withdraw a content block

**Switch persona** to Jonas Weber, content owner. **Go to** `/content`. **Withdraw** VEL-DE-RENAL. **Show** the
block marked Not current with who withdrew it, and the toast "Withdrawn. Drafts now failing their check: inq-103".

**Say:** "Approved content changes. The moment it does, every open draft that used it is checked again."

![Withdraw content](./product-walkthrough-shots/withdraw-content-desktop.webp)

### Approval blocked at send

**Switch persona** to Dr. Lena Brandt, German reviewer. **Go to** `/case?id=inq-103` and press **Approve and
send**. **Show** the two renal sentences marked withdrawn and the toast "Send blocked: the draft no longer
matches current content". Only Reject is offered now.

**Say:** "Even a human approval cannot send stale content. The check runs again at the instant of sending
and fails closed."

![Approve blocked](./product-walkthrough-shots/approve-blocked-desktop.webp)

### A reviewer from the wrong country

**Switch persona** to Dr. Marcus Hale, US reviewer. **Go to** `/case?id=inq-112`, a Japanese draft, and press
**Approve and send**. **Show** the toast "Dr. Marcus Hale may not ApproveReply on inq-112. Verified
Permissions: DENY".

**Say:** "Reviewers approve only in their own country. The refusal is on the ledger too."

![Wrong country reviewer](./product-walkthrough-shots/wrong-country-reviewer-desktop.webp)

## 5. The proof Compliance checks

### Proof

**Go to** `/proof` as Priya Raman, compliance. **Show** the four numbers: ledger intact, adverse events
caught 100%, sentences without a current approved source 0, and model spend.

**Say:** "Four things Compliance checks before trusting this, on one page."

![Proof](./product-walkthrough-shots/proof-desktop.webp)

### Tamper with the ledger

**Press** Change a past entry. **Show** "Entry 22 no longer matches its hash" and the toast that verify now
fails at that entry.

**Say:** "Someone with database access edits a past route. The chain breaks at exactly that row."

![Ledger tamper](./product-walkthrough-shots/ledger-tamper-desktop.webp)

### The archive cannot be deleted

**Press** Restore from the archive, then Try to delete the archive. **Show** the chain verifying again and the
delete refused by Object Lock.

**Say:** "The archived copy is under S3 Object Lock in compliance mode for ten years. Not even the account
owner can delete it."

![Archive locked](./product-walkthrough-shots/archive-locked-desktop.webp)

### Kill switch

**Go to** Automatic replies per country. **Show** the US and Germany switched on with their cleared topics,
and Japan with none.

**Say:** "One switch per country. Turn Germany off and every new reply there goes to a reviewer; nothing
else changes."

![Kill switch](./product-walkthrough-shots/kill-switch-desktop.webp)

### Release gate

**Go to** Release gate. **Show** "Gate passed", the twenty inquiries with expected and actual routes, and the
"Also safe" chip on inq-108, which went to pharmacovigilance instead of a specialist.

**Say:** "A prompt, model or content change ships only if every line holds. One missed adverse event, one
ungrounded sentence or one call to a model other than Haiku 5.5 fails the gate."

![Release gate](./product-walkthrough-shots/release-gate-desktop.webp)
