---
title: Compliant AI for HCP engagement
description: The case study response. Part A is the platform, agentic AI and delivery plan; Part B is the clickable slice and why it was chosen
---

# Compliant AI for HCP engagement

The brief: a global pharma company on AWS talks to healthcare professionals (HCPs) through a CRM, marketing
automation, a contact centre, portals and chatbots. Each channel runs on its own. Doctors get overlapping
messages, product questions take days to route between Medical and Legal, insight cannot be combined across
teams, and nobody can prove that outbound content is current and approved.

This response is in two parts. Part A is the platform and how it would be built and run. Part B is one narrow
slice, built and clickable in this repository, that shows Compliance why each answer is safe, where a human
stays in control, and the moments the system refuses to answer or act.

Everything here is synthetic: Quillon Biopharma, its products Veltrona (an oral tablet for plaque psoriasis)
and Ombrexa (an inhaler for asthma), every doctor and every content block.

## Part A

### 1. What we heard, and the riskiest assumptions

**What we heard**, restated as the problems a platform has to solve:

| Pain in the brief | What it costs | What the platform must do |
|---|---|---|
| Overlapping messages to doctors | Fatigue, opt-outs, and in some countries a breach of promotional limits | One record per doctor across channels, and a check on every planned touch before it goes |
| Product questions take days to route | Doctors wait, reps answer informally, and off-label answers leak | Route each question in seconds to the team that owns it, and answer the safe ones at once |
| Insight cannot be combined | Medical, marketing and field teams each see a slice | A shared timeline and shared events, with access set by role |
| Nobody can prove content is current | An audit finding waiting to happen | Every sentence sent carries the block, version and approval it came from, checked at the moment of sending |

The fourth pain is the one that decides whether AI is allowed in at all. If we cannot prove what was sent and
why, Compliance will not let the AI touch a doctor, and they would be right.

**The riskiest assumptions**, ranked by how badly the plan fails if they are wrong:

1. **Approved content exists as reusable blocks with approval ids.** The whole design answers from approved
   blocks. If medical information content lives only as PDF standard response letters, the first project is
   breaking those letters into blocks inside the existing MLR (Medical, Legal, Regulatory) system. Test it in
   week one by exporting one product's letters from the content system.
2. **Medical will accept replies assembled from verbatim blocks.** Medical information teams already send
   standard response letters, so this is likely, but a reply built from blocks reads less naturally than a
   written letter. Test it by showing five assembled replies to two medical reviewers before building more.
3. **An adverse event screen can reach 100% recall on real messages.** The eval set reaches it; real inboxes
   have typos, other languages and attachments. The design accepts over-reporting (a pharmacovigilance
   specialist spends two minutes) to avoid under-reporting (a reporting breach). Test it by replaying three
   months of real inbound messages, with pharmacovigilance labelling the misses.
4. **One doctor can be matched across systems.** Without a master record, HCP 360 joins the wrong people. Test
   the match rate of CRM, marketing and contact centre ids against the national registries (LANR, NPI) in
   week one.
5. **Country rules can be written as data.** Label scope, promotional caps and disclosure text differ per
   country. If a country's rules need judgement rather than lookup, that country stays fully human.
6. **Claude is available in the regions the data must stay in.** Check Bedrock model availability in the EU
   and Japan regions before committing to automatic replies there.

### 2. Platform architecture

```text
 CRM   Marketing   Contact centre   Portal   Chatbot
   \        |             |           |        /
    +-------+------ EventBridge ------+-------+
            |                         |
        HCP 360                 Inquiry graph -----> Agents (Haiku 5.5, Bedrock in production)
  timeline, consent,        7 nodes, routing table      safety, triage, assembler
  planned touch checks       (Step Functions)           read and select only
            |                         |
            +---- Content store <-----+----> Handoff queues: review, pharmacovigilance
            |   blocks, versions,     |
            |   MLR ids, validity     +----> Audit ledger: hash chain, KMS signed,
            |                                S3 Object Lock archive
     Verified Permissions (Cedar) decides every human action and every agent tool call
```

The platform has four parts, and only one of them uses a model.

**HCP 360.** One record per doctor, keyed on the national registry id, with the ids each source system uses
(CRM, marketing automation, contact centre, portal). Every touch from every channel lands as an event on one
timeline: when, which channel, which product, whether it was promotional, which content block it used. A
planned touch (a campaign email, a rep visit) asks the platform before it goes, and gets a yes or a list of
reasons for no:

- no consent for that channel on record;
- the country's promotional cap for 30 days is reached (two in Germany, four in the US, three in Japan in this
  prototype);
- an open medical information case on the same product, so promotion waits until Medical has answered;
- the content block it uses is no longer current, or is approved for another country.

In production the timeline is fed by change events from each system (Salesforce or Veeva CRM, the marketing
platform, Amazon Connect for the contact centre) through EventBridge, and the operational store is DynamoDB.
The same events land in S3 for analytics under Lake Formation, which is where combined insight comes from.

**How the platform knows content is approved now.** Content is a set of blocks. Each block has an id, a
version, the MLR approval reference, a country, a product, a topic, a valid-from and valid-to date, and a
status. The MLR system stays the source of truth; the platform keeps a read copy that is updated by events.
"Current" is computed, never stored: approved, not withdrawn, and today inside its validity dates.

**What happens when content changes.** A withdrawal or expiry publishes `ContentWithdrawn`. A consumer finds
every open draft and every planned touch that uses the block and checks it again. Drafts are marked failing
and stay failing; nobody can approve them. The check also runs at the instant of sending, against the store
as it is then, so a block withdrawn one second before a human presses Approve still stops the send. The
slice demonstrates exactly this: withdraw `VEL-DE-RENAL` and the German renal draft can no longer be sent.

**Multi-country rules.** Each country is data: its label (which populations and indications are approved),
its promotional cap, its AI disclosure block, the topics cleared for automatic replies and a switch to turn
automatic replies off. People carry a country, and the Cedar policies compare it with the case's country, so
a US reviewer cannot approve a Japanese draft. Data residency follows the country: EU doctors' data stays in
an EU region, and the model is called in that region.

**AWS choices.**

| Job | In this prototype, on Floci | In production | Why |
|---|---|---|---|
| Content, cases, HCP 360, touches | DynamoDB | DynamoDB with point-in-time recovery | Key lookups at any volume, no servers |
| Audit archive | S3 Object Lock, compliance mode, 10 years | Same, in a separate audit account | Nobody, including the root user, can delete it |
| Ledger checkpoints | KMS asymmetric signing key | Same, key held in the audit account | Compliance can verify without trusting the app team |
| Permissions | Verified Permissions with Cedar | Same | Policies are readable by Compliance, testable, and every decision is logged |
| People and roles | Cognito user pool | IAM Identity Center federated to the company IdP | Joiners and leavers are handled where they already are |
| Routing | Step Functions, generated from the routing table | Express workflows, one per inquiry | The route is a reviewed artefact, not code inside a prompt |
| Handoffs | EventBridge to SQS | Same, plus connectors into the safety database and Veeva | Each team's tool consumes its own queue |
| Per-country autonomy | SSM Parameter Store | AppConfig with staged rollout and rollback | A kill switch that takes effect without a deploy |
| Metrics and logs | CloudWatch | CloudWatch, plus Langfuse traces per agent call | Operations and model quality on separate dashboards |
| Model | Claude Haiku 5.5 through the Claude Agent SDK | Claude on Amazon Bedrock in-region, with Bedrock Guardrails | Data stays in the account and region |

Floci emulates these services locally, so the whole platform starts with `make up` and no cloud account, and
the code that talks to Floci is the same boto3 code that talks to AWS.

### 3. Agentic AI in a regulated setting

**The rule underneath everything:** the model never writes a sentence a doctor reads, and never chooses
where a case goes. It reads, classifies and selects. Code decides and composes.

**What is autonomous, what needs a human, what gets no AI.**

| The AI does on its own | A human in the loop decides | No AI at all |
|---|---|---|
| Screen every message for adverse events and special situations | Any reply on a topic not cleared for automatic sending in that country | Adverse event and special situation handling (pharmacovigilance) |
| Split a message into questions and tag topic, population and indication | Any reply where approved content does not cover every question | Off-label answers, which Medical writes |
| Pick the approved block ids that answer each question | Senders who are not verified HCPs, unknown products | Writing or editing any medical sentence |
| Send a reply when every rule passes and the topic is cleared | Turning automatic replies on or off per country | Approving content, which stays in MLR |

**The graph.** Seven nodes run in a fixed order: intake, safety screen, classify, scope check, assemble,
verify, autonomy. Each node establishes facts (`ae`, `verified_hcp`, `intent`, `in_scope`, `covered`,
`grounded`, `auto_allowed`). After every node an engine walks a ten-rule routing table in order; the first
rule whose fact matches decides the route, and a rule whose fact is still unknown makes the engine wait for
the next node instead of guessing. Safety comes first, so an adverse event stops the graph before the model
has even classified the question. The table is the policy; the same table generates the Step Functions
definition. Tests walk every combination of facts through the table, and run one case per rule through
Step Functions on Floci to check it routes like the Python engine.

**Three agents, each with one job.** All three run on the Claude Agent SDK, pinned to `claude-haiku-5-5`,
with no built-in tools, no settings files, no slash commands and structured JSON output.

- The **safety agent** returns possible adverse events and special situations with verbatim quotes. Keyword
  rules run beside it; either one is enough. The agent can add signals, never remove them.
- The **triage agent** splits the message into questions and tags each one. A keyword screen for attempts to
  change the rules runs beside it; either one is enough to decline.
- The **assembler agent** searches approved content through two read-only MCP tools and returns block ids per
  question. It cannot see withdrawn or expired blocks, and it cannot write text.

**Guardrails, in the order they fire.**

1. The inquiry text is wrapped as untrusted data; a test checks it cannot close its own wrapper.
2. Every tool call passes a guard: the tool must be on an allowlist and target the case's own country and
   product, and then Verified Permissions must allow it (`agents.cedar`). Denied calls are recorded.
3. Agent output must match a JSON schema, and a block id survives only if it exists, belongs to the case's
   product and country, and a permitted tool call actually returned it.
4. Every sentence of the composed reply must match a sentence in a current approved block for this product
   and country; the safety information block and the AI disclosure block must be present.
5. The same check runs again at the instant of sending, and fails closed.
6. A spend cap per case and per session, computed from tokens, stops live calls; any model other than Haiku
   5.5 fails the run.

**Handoffs and recording.** A case that needs a human is published to EventBridge and lands in that team's
SQS queue: `ReviewNeeded` for Medical, `SafetySignal` for pharmacovigilance with the quoted words and the
date received (day zero for the reporting clock). Every step appends to the audit ledger: the case received
(with a hash of the text, not the text), each agent call with model, prompt version and tokens, each tool
call with its guard and Cedar decision, the route and the rule that chose it, every approval, rejection,
withdrawal and permission refusal.

**Traceability.** From any sentence a doctor received you can walk back to the block, its version and its MLR
approval; from the case to the agent calls, the prompt version and the recorded model output; from any human
action to the Cedar policy file that allowed or refused it. Each ledger entry carries the hash of the one
before it, every entry is copied to S3 under Object Lock, and the chain head is signed with KMS every ten
entries.

**Proving it is safe to Compliance.** Not with a slide. Compliance gets:

- the routing table and the Cedar policies, which are short enough to read;
- the release gate: every change to a prompt, the model or the content runs twenty inquiries through the
  graph and fails on one missed adverse event, one ungrounded sentence, one unsafe automatic send or one call
  to another model (`evals/gate.toml`);
- the ledger, which they can verify themselves, and the archive, which nobody can delete;
- the kill switch per country, which they hold.

**Regulation this design answers.** Pharmacovigilance rules (EU GVP Module VI) start the reporting clock when
anyone in the company, including a system, first receives the information, so the safety screen runs first
and routes at once. Off-label promotion rules mean unsolicited off-label questions get a scientific answer
written by Medical, never a generated one. The EU AI Act's transparency duty (Article 50) is met by an AI
disclosure block in every assembled reply; a medical information triage system is not obviously high-risk
under Annex III, but this design keeps the record-keeping, human oversight and accuracy evidence the
high-risk articles ask for, so a reclassification costs paperwork, not a rebuild. Automated Reasoning checks
in Bedrock Guardrails are a candidate second verifier for policy statements in production.

### 4. Engineering practices

- **Decisions are written down.** Each architecture decision is an ADR in `docs/adr/` with the options
  considered and the failure it prevents.
- **One gate.** `make check` runs the unit and end-to-end tests on Floci, the eval gate, the mutation run,
  the prose check, the web build and a parse of every mermaid diagram. A check that is not in `make check`
  does not exist.
- **Tests that bite.** `scripts/mutate.py` breaks each safety property in turn (the adverse event rule, the
  injection rule, content currency, the check at send, the tool guard, the model pin and two Cedar
  policies) and fails the gate if no test catches it. Writing it found two tests that passed for the wrong
  reason; both were fixed.
- **Model changes are releases.** The model id, prompt version and price table live in one module; a new
  prompt version needs a new recording and a green gate. Replay is the default, so CI and demos cost nothing
  and give the same answer every time; `LIVE=1` re-records.
- **Release safety.** Automatic replies roll out per country and per topic through AppConfig, starting with
  four weeks where every draft is approved by a human. The kill switch takes effect without a deploy.
- **Monitoring.** Route counts, latency, cost per case and queue depth in CloudWatch; per-call traces with
  prompt, output and tokens in Langfuse; alerts on a rise in declined or pharmacovigilance routes, on any send
  blocked at the last check, and on a broken ledger.
- **AI tools used to build it.** Claude Code with the repository's own `.claude/` folder: path-scoped rules
  for the agents and policies, a compliance reviewer subagent that reads any diff touching routing, guards or
  Cedar, skills for adding a content block and recording a new prompt version, and a hook that refuses any
  model id other than Haiku 5.5.

### 5. First release and how we measure it

**Scope.** One country (Germany), one product (Veltrona), two channels (portal and email), and the medical
information inquiry flow end to end, with HCP 360 holding planned touches for that product. Automatic replies
stay off for the first four weeks; the AI drafts and a human approves every reply. Then Compliance clears
dosing, administration and storage, one topic at a time, based on the reviewer approval rate for that
topic.

**Out of scope for the first release:** other countries, chatbots, rep-entered questions, and any
promotional content generation.

**Success measures.**

| Measure | Baseline to capture in week one | Target at 90 days |
|---|---|---|
| Time to first reply, cleared topics | Days | Under five minutes |
| Time to first reply, everything else | Days | Same working day |
| Adverse events reaching pharmacovigilance | Unknown | 100% of the eval set, every release; under one hour from receipt |
| Sentences sent without a current approved source | Unknown | Zero, checked by the ledger |
| Drafts approved without edits | Not applicable | Above 90% before a topic is cleared |
| Planned touches held for cap, consent or open case | Unknown | Reported weekly to brand teams |
| Model cost per case | Not applicable | Under one cent |

## Part B: the slice

### What it is

The medical information inquiry flow: an unsolicited question from a doctor, on any channel, through the
graph to a reply, a reviewer or the team that owns it. Run it with `make up && make serve` and open
`http://localhost:8765`. The [product walkthrough](./product-walkthrough.md) is a screen-by-screen script.

### Why this slice

It is where all four pains meet, and where the regulatory stakes are highest. A product question is the
moment a doctor waits for days; it can contain an adverse event with a legal clock; it can be off-label; and
the reply is outbound content that must be current and approved. If Compliance trusts the AI here, every
other channel is easier. If they do not, nothing else matters.

It also shows the moments the system must not answer or act, which a happy-path demo hides:

| The system does not | When | Screen |
|---|---|---|
| Answer | A possible adverse event or special situation | `/case?id=inq-105` |
| Draft anything | The question is off-label in that country | `/case?id=inq-104` |
| Draft anything | The message tries to change the rules | `/case?id=inq-107` |
| Send without a human | The topic is not cleared in that country | `/case?id=inq-103` |
| Send at all | A block was withdrawn after drafting, even with a human approval | `/case?id=inq-103` after a withdrawal |
| Let a person act | A reviewer from another country, a rep reading case detail | `/case?id=inq-112`, `/case?id=inq-105` |
| Send a planned promotion | Over the country cap, or with an open medical case | `/hcp?id=hcp-kaya` |

### How each screen works in production

| Screen | In production |
|---|---|
| Inbox | Not a screen: questions arrive from the portal, email, Amazon Connect and the CRM through EventBridge |
| Case | The audit view in the medical information tool; the same data, read from the ledger |
| Review bench | The reviewer's queue in the existing medical information system, fed by `ReviewNeeded` |
| HCP 360 | An API every channel calls before a touch; the screen is for brand and field managers |
| Content | The MLR system stays the source; withdrawals arrive as events |
| Proof | Compliance's dashboard, plus the ledger verifier as a scheduled job that alerts on a break |

### Edge cases handled

- A question with two parts, one on-label and one off-label: the whole case goes to Medical; there is no
  partial automatic reply.
- The same question is on-label in the US and off-label in Germany: scope is per country.
- An adverse event written in German: the English keyword rules miss it, the safety agent catches it, and the
  eval set includes it.
- A patient, not a doctor, writes in: an unverified sender never gets an automatic reply.
- An expired block: it is not evidence, so the case goes to review with no draft.
- A rep reports a side effect they heard about: pharmacovigilance, whatever the channel.
- Content withdrawn between draft and approval: the send is blocked at the last check.

### Open questions for the client

1. Which system holds approved medical information content today, and does it carry block-level approval
   ids?
2. Who in each country can clear a topic for automatic replies, and what evidence do they want first?
3. What is pharmacovigilance's intake system, and does it accept an event with quotes and a day zero?
4. Is there a master HCP record today, or does the platform need to build the match?
5. Which regions must data stay in, country by country?
6. Does Legal want the AI disclosure in every reply, including ones a human approved?
7. How long must the audit archive be kept; is ten years right for every country?

## Sources

- Floci, local AWS emulator: <https://floci.io/>
- Claude Agent SDK: <https://code.claude.com/docs/en/agent-sdk/overview>
- Amazon Bedrock Guardrails: <https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html>
- Amazon S3 Object Lock: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html>
- Amazon Verified Permissions: <https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/what-is-avp.html>
- EU AI Act, Article 50: <https://artificialintelligenceact.eu/article/50/>
- EMA, Good Pharmacovigilance Practices, Module VI: management and reporting of adverse reactions
- FDA, Communications from firms to health care providers regarding scientific information on unapproved uses
- CIOMS Working Group XIV, artificial intelligence in pharmacovigilance
