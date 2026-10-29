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

The platform is a system of agents under one control plane, not one agent and not a pipeline with agents as
steps. The [architecture walkthrough](./architecture-walkthrough.md) follows one doctor through it in four
acts, with a diagram per step. This section is the summary.

```text
 CRM   Marketing   Contact centre   Portal   Chatbot
   \        |             |           |        /
    +-------+---- signed webhooks and batch ---+
            |
   Identity resolution --> HCP 360 timeline (the agents' shared memory)
            |                       |
   Eight agents (Temporal workflows, LangGraph inside) <--- events (EventBridge, SQS)
            |
   Control plane: policy kernel, Cedar, autonomy ladder, model router, AI gateway,
                  eval gate and releases, ledger
            |
   Data plane: Postgres (row-level security, pgvector), Valkey, S3 Object Lock, KMS per tenant
```

**Four planes.** The agent plane holds eight long-lived agents. The control plane holds everything no agent
may override. The data plane holds state, search, events and the archive. The interface plane is the
console, the `/v1` API, an MCP server, the `hcp` CLI and the channel webhooks.

**HCP 360.** One record per doctor, keyed on the national registry id, with the ids each source system uses.
Every touch from every channel lands as an event on one timeline. Webhooks are signed and land once; a nightly
batch is a Temporal schedule; an id nobody can match stays unlinked rather than guessed. A planned touch asks
the platform before it goes and gets a yes or a list of reasons for no:

- no consent for that channel on record;
- the country's promotional cap for 30 days is reached (two in Germany, four in the US, three in Japan in this
  prototype);
- an open medical information case on the same product, so promotion waits until Medical has answered;
- the content block it uses is no longer current, or is approved for another country.

**How the platform knows content is approved now.** Content is a set of blocks with an id, a version, the MLR
approval reference, a country, a product, a topic, validity dates and a status. The MLR system stays the source
of truth; the platform keeps a read copy updated by events. "Current" is computed, never stored.

**What happens when content changes.** A withdrawal or expiry publishes `ContentWithdrawn`. The content
steward finds every open draft and planned touch that uses the block, pulls them back to review and evicts
the cache. The check also runs at the instant of sending, against the store as it is then, so a block
withdrawn one second before a human presses Approve still stops the send. Withdraw `VEL-DE-RENAL` in the
console and the German renal draft can no longer be sent.

**Multi-tenant, multi-country.** Quillon Biopharma is the first tenant and Marlowe Therapeutics the second.
The tenant comes from the signed token, Postgres row-level security filters every row, and Cedar refuses a
crossing. Each country is data: its label, promotional cap, AI disclosure block, cleared topics and an
automatic-reply switch. A US reviewer cannot approve a Japanese draft.

**AWS choices.**

| Job | Locally on Floci and Docker | In production (CDK, synthesized and never deployed here) | Why |
|---|---|---|---|
| State, search | Postgres with pgvector | Aurora Postgres | Row-level security and joins decide it (ADR 0009) |
| Cache, rate limits | Valkey | ElastiCache | The cache only forgets, so it can fail safely |
| Audit archive | S3 Object Lock, compliance mode, 10 years | Same, one bucket and key per tenant | Nobody, including the root user, can delete it |
| Ledger checkpoints | KMS asymmetric signing key | Same | Compliance can verify without trusting the app team |
| Permissions | Verified Permissions with Cedar | Same | Policies are readable by Compliance and every decision is logged |
| People and roles | Cognito user pool | Cognito, federated to the company identity provider | A user cannot write their own role or tenant |
| Durable work | Temporal dev server | A Temporal cluster the stack takes as an input | Waits of days, timers and crash resume |
| Events | EventBridge to SQS, with a dead-letter queue | Same, plus connectors to the safety database | Each team's tool consumes its own queue |
| Services | One image, two processes | ECS Fargate for the API and the worker | No Kubernetes for two stateless services (ADR 0031) |
| Models | Claude Haiku 5.5 and Sonnet 5.5 through our AI gateway | Same; a Bedrock adapter is not built | The router picks the model, the gateway meters it |

### 3. Agentic AI in a regulated setting

**The rule underneath everything:** the model never writes a sentence a doctor reads, and never chooses where
a case goes. It reads, classifies, plans and selects. Code decides and composes.

**Eight agents, each with a goal and a limit.** `world/agents.toml` is the roster and the Agents page shows it.

| Agent | Acts alone | Only proposes | Never |
|---|---|---|---|
| Safety sentinel | Opens a pharmacovigilance case, freezes contact | Nothing | Assesses causality |
| Inquiry agent | Plans, retrieves, selects, asks a clarifying question | Drafts outside cleared topics | Writes medical text |
| Outreach coordinator | Holds a duplicate or conflicting send | Every new contact | Contacts without consent |
| Content steward | Pulls impacted drafts back to review | Content requests | Edits content |
| Insight agent | Writes traced digests for internal teams | Themes for Medical Affairs | Anything to a doctor |
| Guardian | Trips a kill switch, lowers autonomy | Raising it back | Raises autonomy |
| Improver | Runs candidates against the gate | A new prompt or router | Promotes anything |
| Supervisor | Assigns and breaks ties by policy | Conflicts it cannot settle | Overrides the kernel |

The rule: **an agent acts alone only in the direction that lowers risk.** Sending, contacting and promoting
are proposals, and some actions are never available.

**The policy kernel.** Agents choose how to do a step. The kernel owns which steps exist, their order, which
facts each may set and the route those facts imply. A ten-rule routing table is walked in order after every
step; the first rule that matches decides, and a rule whose fact is unknown waits instead of guessing. Safety
comes first, so an adverse event stops the case before the model has classified the question. A plan that
skips the screen, rewrites a fact or loops past its limit is refused and the case goes to a person. The
same table generates the Step Functions definition, so a picture of it cannot drift from the code.

**Model routing.** A pure function picks Haiku 5.5 for high-volume work, Sonnet 5.5 for planning and any
failed try, and a person after that or when the budget is gone. Nothing else can be returned.

**Guardrails, in the order they fire.**

1. The inquiry text is wrapped as untrusted data; a test checks it cannot close its own wrapper.
2. Every tool call passes a guard: the tool must be on an allowlist and target the case's own country and
   product, and then Verified Permissions must allow it.
3. Agent output must match a JSON schema, and a block id survives only if it exists, belongs to the case's
   product and country, and a permitted call actually returned it.
4. Every sentence of the composed reply must match a sentence in a current approved block, and the safety
   information and AI disclosure blocks must be present.
5. The same check runs again at the instant of sending, and fails closed.
6. Every model call goes through the AI gateway, which holds a virtual key per tenant and agent, a budget and
   a spend log. A call off the two-model allowlist fails the gate.

**Always on and durable.** A case that needs a reviewer is a Temporal workflow that waits. A worker crash
resumes it where it stopped and finishes it once, an SLA timer escalates a case nobody has taken, and approval
asks the reviewer for their password again, which is the electronic signature. Every consumer is idempotent
and a message that keeps failing lands in a dead-letter queue.

**Handoffs and recording.** A case that needs a human is published to EventBridge and lands in that team's
SQS queue: `ReviewNeeded` for Medical, `SafetySignal` for pharmacovigilance with the quoted words and the date
received (day zero for the reporting clock). Every step appends to the hash-chained ledger, with personal
data sealed under a key per person, so erasing a person deletes the key and leaves the chain intact.

**Traceability.** From any sentence a doctor received you can walk back to the block, its version and its MLR
approval; from the case to the agent calls, the prompt version, the release and the trace; from any human
action to the Cedar policy file that allowed or refused it. Each ledger entry carries the hash of the one
before it, is copied to S3 under Object Lock, and the chain head is signed with KMS every ten entries.

**Self-improvement, proven per release.** A release pins the prompts, the router, the retrieval setup and the
policy table and gets a hash for an id. Reviewer corrections become proposals from the improver, which
promotes nothing. A candidate release runs the eval gate: safety metrics are absolute (adverse-event recall
1.0, zero ungrounded sentences, zero unsafe automatic sends, zero off-allowlist calls), and quality and cost
are compared with the baseline release. A person promotes it. The Releases page shows each metric across
releases, and the guardian trips a country's kill switch if reviewers start rejecting drafts.

**Proving it is safe to Compliance.** Not with a slide. Compliance gets:

- the routing table and the Cedar policies, which are short enough to read;
- the release gate and its history per release (`evals/gate.toml`, the Releases page);
- the ledger, which they can verify themselves, and the archive, which nobody can delete;
- the kill switch per country, which they hold;
- a [validation pack](./validation-pack.md) that maps each requirement to the test and the mutant that
  enforce it, and an [EU AI Act classification](./eu-ai-act.md).

**Regulation this design answers.** Pharmacovigilance rules (EU GVP Module VI) start the reporting clock when
anyone in the company, including a system, first receives the information, so the safety screen runs first
and routes at once, and the sentinel reads every channel so nobody has to ask. Off-label promotion rules mean
unsolicited off-label questions get a scientific answer written by Medical, never a generated one. The EU AI
Act's transparency duty (Article 50) is met by an AI disclosure block in every assembled reply.

### 4. Engineering practices

- **Decisions are written down.** Each architecture decision is an ADR in `docs/adr/` with the options
  considered and the failure it prevents.
- **One gate.** `make check` runs the tests, the evals, the mutation run, the prose check, the web build, a
  parse of every mermaid diagram, `cdk synth` with cdk-nag and the coverage matrix. A check that is not in
  `make check` does not exist.
- **Tests that bite.** `scripts/mutate.py` breaks each safety property in turn and fails the gate if no test
  catches it.
- **Model changes are releases.** The model ids, prompt versions and price table live in one place; a new
  prompt version needs a new release and a green gate. Replay is the default, so CI and demos cost nothing and
  give the same answer every time; `LIVE=1` runs the real models.
- **Release safety.** Automatic replies are switched on per country and per topic, starting with four weeks
  where every draft is approved by a human. The kill switch takes effect without a deploy.
- **Monitoring.** Per-call traces in OpenTelemetry's GenAI conventions with personal data redacted, exported to
  Phoenix locally or Langfuse Cloud by environment; cost, override rate and latency split by release.
- **Supply chain.** GitHub Actions runs the gate, SAST, an SBOM, secret scanning and a dependency audit.
- **AI tools used to build it.** Claude Code with the repository's own `.claude/` folder: path-scoped rules
  for the agents and policies, skills for adding a content block and recording a prompt version, and a hook
  that refuses any model id outside the two allowed.

### 5. First release and how we measure it

**Scope.** One country (Germany), one product (Veltrona), two channels (portal and email), and the medical
information inquiry flow end to end, with HCP 360 holding planned touches for that product. Automatic replies
stay off for the first four weeks; the AI drafts and a human approves every reply. Then Compliance clears
dosing, administration and storage, one topic at a time, based on the reviewer approval rate for that topic.

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

**Known limits of this build.** Autonomy settings and queues are shared across tenants. There is no Bedrock
failover adapter. Sign-in is a password exchange, not an OAuth device flow, and the MCP server hosts no OAuth
server. The CDK stack has no migration task, blue/green deploy or second region. The `hcp_app` database role
in `migrations/001_documents.sql` has a local-only password that production sets from Secrets Manager. The
static console sets no content security policy of its own.

## Part B: the slice

### What it is

The medical information inquiry flow: an unsolicited question from a doctor, on any channel, through the
inquiry agent, bounded by the policy kernel, to a reply, a reviewer or the team that owns it. The slice also
shows the other agents at work: the sentinel, the outreach coordinator and the content steward. Run it with `make up && make serve` and open
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
- An adverse event written in German: the English keyword rules miss it, the safety sentinel catches it, and the
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
