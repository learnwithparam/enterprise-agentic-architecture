---
title: Architecture walkthrough
description: How the agentic system is built, one doctor at a time, with the layer that each step needs and the diagrams that show it
---

# Architecture walkthrough

This is a system of agents, not one agent and not a workflow with agents as steps. Eight goal-driven
agents live for a long time, perceive events from every channel, coordinate through shared state, act
alone only where that lowers risk, and improve from what reviewers correct. A control plane that
Compliance can read bounds all of them.

The walkthrough follows one doctor through the platform in four acts. A layer appears at the moment the
step before it breaks without it. Each step names the problem, the choice, the code and the test.

## The system at a glance

```mermaid
flowchart LR
  hcp(["Doctors"])
  chan["Portal, email, contact centre,<br/>chatbot, field CRM"]
  teams(["Medical, Compliance,<br/>Pharmacovigilance, Marketing, Field"])
  mlr["MLR system<br/>approved content"]
  pvdb["Safety database"]
  sys["Quillon MI platform"]
  clients(["A client's own agents<br/>and scripts"])
  hcp --> chan --> sys
  teams <--> sys
  mlr --> sys
  sys --> pvdb
  clients <--> sys
```

The platform serves more than one client. Quillon Biopharma is the first tenant and Marlowe Therapeutics
the second; no row, key or queue is shared between them.

## The four planes

```mermaid
flowchart TB
  subgraph interface["Interface plane"]
    console["Next.js console"]
    v1["/v1 API and SSE"]
    mcp["MCP server"]
    cli["hcp CLI"]
    hooks["Channel webhooks"]
  end
  subgraph agent["Agent plane"]
    agents["Eight agents, each a long-lived Temporal workflow<br/>with an inner LangGraph for its reasoning"]
  end
  subgraph control["Control plane"]
    kernel["Policy kernel"]
    cedar["Cedar in Verified Permissions"]
    router["Model router"]
    gateway["AI gateway"]
    gate["Eval gate and releases"]
    ledger["Ledger"]
    registry["Agent roster"]
  end
  subgraph data["Data plane"]
    pg[("Postgres with row-level security<br/>and pgvector")]
    valkey[("Valkey")]
    bus["EventBridge and SQS"]
    s3[("S3 Object Lock")]
  end
  interface --> agent
  agent --> control
  agent --> data
  control --> data
```

| Plane | Owns | Modules |
|---|---|---|
| Interface | How people and other systems reach the platform | `api.py`, `v1.py`, `mcp_server.py`, `cli.py`, `ingest.py`, `web/` |
| Agent | Goals, plans, tools, hand-offs | `agents.py`, `plan.py`, `sentinel.py`, `outreach.py`, `supervisor.py`, `insight.py`, `guardian.py`, `improver.py` |
| Control | What no agent may do, who may do what, which model, what it costs, whether a release is better | `kernel.py`, `graph.py`, `authz.py`, `router.py`, `gateway.py`, `releases.py`, `ledger.py` |
| Data | State, search, events, the archive | `store.py`, `db.py`, `retrieval.py`, `cache.py`, `events.py` |

## The agents

```mermaid
flowchart LR
  subgraph perceive["What they perceive"]
    inq["Inquiries"]
    notes["Rep notes and call transcripts"]
    mlrev["MLR events and expiries"]
    t360["HCP 360 timeline"]
    sig["Budgets, drift, override rate"]
    fb["Reviewer corrections"]
  end
  sentinel["Safety sentinel"]
  inquiry["Inquiry agent"]
  steward["Content steward"]
  outreach["Outreach coordinator"]
  insight["Insight agent"]
  guardian["Guardian"]
  improver["Improver"]
  supervisor["Supervisor"]
  inq --> sentinel & inquiry
  notes --> sentinel
  mlrev --> steward
  t360 --> outreach & insight
  sig --> guardian
  fb --> improver
  outreach --> supervisor
  inquiry --> supervisor
  sentinel -- "opens a PV case, freezes contact" --> supervisor
```

`world/agents.toml` holds one row per agent: its goal, what it perceives, what it does alone, what it only
proposes, what it never does and which model class it uses. `GET /api/agents` joins each row with its
calls and cost, and the Agents page shows it (ADR 0030). The rule underneath: **an agent acts alone only in
the direction that lowers risk.** Sending, contacting and promoting are proposals. Overriding the kernel,
assessing causality and raising anyone's autonomy are never available.

## Act 1: one question, answered safely

### 1. Who is asking, and for which client?

A question arrives, and the first thing the platform needs is an identity and a tenant, both from a signed
token and never from a header the caller controls.

- `auth.py` verifies the token against the identity provider's keys and takes the tenant from it (ADR 0010).
- `db.py` sets `app.tenant_id` on every connection and Postgres row-level security does the rest (ADR 0009).
- Cedar refuses a crossing between tenants (`policies/cedar/tenants.cedar`, ADR 0011).

```mermaid
flowchart LR
  req["Request with a bearer token"] --> mw["Middleware: verify token"]
  mw -- "no or bad token" --> r401["401"]
  mw --> ctx["Tenant set for this request"]
  ctx --> route["Route"]
  route --> db[("Postgres: RLS filters every row")]
  route --> az["Cedar: may this person do this?"]
  az -- "DENY" --> r403["403, and the refusal is on the ledger"]
```

Tests: every route needs a token, every table has row-level security, and a tenant B user gets nothing of
tenant A's through the API, MCP or the CLI.

### 2. It may hide an adverse event or an injection

`rules.py` screens every message with keywords that never depend on a model, and the safety agent quotes
the passage. A possible adverse event goes to pharmacovigilance whatever else the message asks, and the
model never sees it again. The **policy kernel** (`kernel.py`, from the routing table in `graph.py`) is
what makes this hold: it checks every step an agent plans against the table, and any plan that would skip
a safety step is refused (ADR 0013).

```mermaid
flowchart TD
  start(["intake"]) --> r1{"possible adverse event?"}
  r1 -- yes --> pv["route: pharmacovigilance"]
  r1 -- no --> r2{"injection attempt?"}
  r2 -- yes --> dec["route: declined"]
  r2 -- no --> r3{"inside the label?"}
  r3 -- no --> ol["route: off-label, medical writes"]
  r3 -- yes --> plan["plan, retrieve, select"]
  plan --> r4{"every sentence grounded?"}
  r4 -- no --> rev["route: medical review"]
  r4 -- yes --> r5{"topic cleared in this country?"}
  r5 -- no --> rev
  r5 -- yes --> send["route: sent automatically"]
```

The diagram is a picture of `graph.ROUTING`, and `graph.asl()` emits the same table as a Step Functions
definition. A new rule is one row in that table, never an edge somewhere else.

### 3. The inquiry agent plans

The inquiry agent splits the message into questions, retrieves, selects blocks, checks that every
question is covered and tries once more if not (`plan.py`, a LangGraph graph; ADR 0014). It is a bounded
loop: it cannot run more than a fixed number of cycles, and the kernel checks every transition. The model
chooses block ids. It never writes a sentence a doctor reads (ADR 0002).

```mermaid
sequenceDiagram
  participant C as Case
  participant K as Kernel
  participant P as plan.py (LangGraph)
  participant R as Router
  participant G as AI gateway
  participant T as MCP tools
  C->>K: step allowed?
  K-->>C: yes
  C->>P: split, retrieve, select
  loop at most a fixed number of cycles
    P->>R: which model for this call?
    R-->>P: Haiku 5.5, or Sonnet 5.5 after a failure
    P->>G: call with tenant, agent, release, prompt version
    G-->>P: block ids
    P->>T: search_approved_content, get_block
    P->>P: every question covered?
  end
  P-->>C: ids per question
  C->>C: keep only ids a permitted call returned
```

Model routing (`router.py`, ADR 0008): Haiku 5.5 is the default for high-volume work and Sonnet 5.5 takes
planning, arbitration and synthesis. A schema failure escalates once to Sonnet, then goes to a person.
`.claude/hooks/model_allowlist.py` and `tests/test_claude_config.py` refuse any other model id (ADR 0007).

### 4. What may we say?

`retrieval.py` searches approved content in two stages (ADR 0012). The **facet filter** (tenant, product,
country, population, topic, language, approval state) is a hard gate: nothing outside it is ever a
candidate. Inside it, Postgres full-text and pgvector ranks are fused by reciprocal rank fusion. Embeddings
come from `embeddings.py`, a port with a local multilingual model by default, so no key is needed and the
provider is a config choice. Vectors store the model id and dimension, so two models never mix.

```mermaid
flowchart LR
  q["Question"] --> facet["Facet gate:<br/>tenant, product, country,<br/>population, topic, language, approved"]
  facet --> fts["Full-text rank"]
  facet --> vec["Vector rank"]
  fts --> rrf["Reciprocal rank fusion"]
  vec --> rrf
  rrf --> top["Top blocks"]
  cache[("Valkey cache")] -. "only forgets" .-> top
```

`retrieval_eval.py` scores recall at k on `world/retrieval.toml`, including other-language questions, and
the gate fails if hybrid falls below its thresholds. A mutant that drops the facet gate is killed.

### 5. Prove every sentence

`grounding.compose` places the selected blocks verbatim between fixed templates. `grounding.verify` checks
each sentence against the content store as it is now, for that product and country. It runs again at the
instant of sending, so a block withdrawn while a draft waited can never go out.

### 6. May it go alone?

The autonomy ladder decides. Only an on-label question, fully covered by current content, on a topic
Compliance has cleared for that country, is sent without a person. Cedar decides every action that follows.

| Agent | Acts alone | Proposes | Never |
|---|---|---|---|
| Safety sentinel | opens a PV case, freezes contact | nothing | assesses causality |
| Inquiry agent | plans, retrieves, selects, asks a clarifying question | drafts outside cleared topics | writes medical text |
| Outreach coordinator | holds a duplicate or conflicting send | every new contact | contacts without consent |
| Content steward | pulls impacted drafts back to review | content requests | edits content |
| Insight agent | writes traced digests for internal teams | themes for Medical Affairs | anything to a doctor |
| Guardian | trips a kill switch, lowers autonomy | raising it back | raises autonomy |
| Improver | runs candidates against the gate | a new prompt or router | promotes anything |
| Supervisor | assigns, breaks ties by policy | conflicts it cannot settle | overrides the kernel |

### 7. Record it so nobody can edit it

`ledger.py` hashes every entry with its predecessor, stores it in Postgres and copies it to an S3 Object
Lock bucket (compliance mode, ten years), and signs the head with KMS every tenth entry (ADR 0005). Personal
data in an entry is sealed under a key per person, so erasing a person deletes the key and leaves the chain
intact (`privacy.py`, ADR 0015).

```mermaid
flowchart LR
  e1["Entry n<br/>hash(entry, hash n-1)"] --> e2["Entry n+1"] --> e3["Entry n+2"]
  e1 -. "copy" .-> s3[("Object Lock archive")]
  e2 -. "copy" .-> s3
  e3 -. "every tenth: signed head" .-> kms["KMS signature"]
```

## Act 2: always on

### 8. A reviewer takes two days

A case that needs a reviewer is a Temporal workflow that waits (`workflows.py`, ADR 0016, 0017). Temporal's
history is the only durable record of where it is. A worker crash resumes the case where it stopped and
finishes it once. An SLA timer escalates a case nobody has taken. Approval takes the reviewer's password
again, which is the electronic signature in the 21 CFR Part 11 sense.

```mermaid
stateDiagram-v2
  [*] --> running: inquiry arrives
  running --> sent: route sent automatically
  running --> awaiting_review: needs a person
  running --> with_pharmacovigilance: possible adverse event
  running --> declined: injection attempt
  awaiting_review --> sent: approved with re-authentication
  awaiting_review --> rejected: rejected with a note
  awaiting_review --> blocked_at_send: content changed, check failed
  awaiting_review --> awaiting_review: SLA timer fires, escalates
  sent --> [*]
  rejected --> [*]
  blocked_at_send --> [*]
```

```mermaid
sequenceDiagram
  actor Doctor
  participant W as Temporal worker
  participant T as Temporal history
  actor Reviewer
  Doctor->>W: question
  W->>T: record: draft ready, waiting for a reviewer
  Note over W: worker crashes
  W->>T: new worker replays the history
  Reviewer->>W: signal: approve, with password
  W->>W: verify against current content
  W->>T: record: sent, once
```

### 9. A block is withdrawn mid-review

The content steward listens for `ContentWithdrawn`, pulls every impacted draft back to review, re-verifies
and evicts the cache (ADR 0018). The cache only ever forgets: a stale entry can make a case slower, never
different.

```mermaid
sequenceDiagram
  actor Owner as Content owner
  participant C as Cases
  participant B as EventBridge and SQS
  participant S as Content steward
  participant K as Valkey
  actor Reviewer
  participant L as Ledger
  Owner->>C: withdraw VEL-DE-RENAL
  C->>L: content_withdrawn
  C->>B: ContentWithdrawn
  B-->>S: event
  S->>K: evict cached retrievals
  S->>L: draft_invalidated for each impacted case
  Reviewer->>C: approve an impacted draft
  C->>C: verify against the store as it is now
  C->>L: send_blocked with the problems
  C-->>Reviewer: nothing was sent
```

### 10. The provider fails, and finance asks what each tenant costs

Every model call goes through `gateway.py`, a thin gateway of our own that speaks the Anthropic Messages
API (ADR 0019). It holds a virtual key per tenant and agent, budgets, failover between providers and a
spend log row for every call tagged with tenant, agent, release, prompt version and case. The Agent SDK is
pointed at it with `ANTHROPIC_BASE_URL`, so even tool-using calls are metered. Delivery is at least once, so
every consumer is idempotent and a message that keeps failing lands in a dead-letter queue with replay
(ADR 0020).

```mermaid
flowchart LR
  agent["Agent call"] --> router["Router: Haiku 5.5 or Sonnet 5.5"]
  router --> gw["AI gateway"]
  gw --> budget{"within the budget<br/>of this tenant and agent?"}
  budget -- no --> refuse["Refused, logged"]
  budget -- yes --> prov["Anthropic API"]
  prov -- "fails" --> alt["Next provider"]
  prov --> log[("Spend log: tenant, agent,<br/>release, prompt version, case")]
  alt --> log
```

## Act 3: one doctor, many channels, many agents

### 11. Three teams are about to message the same doctor

`ingest.py` accepts events from the CRM, marketing, the contact centre and the portal, each signed with an
HMAC and landed once (ADR 0021). `identity.py` resolves a channel's own id to one doctor, and an unknown
handle stays unlinked rather than guessed (ADR 0022). `hcp360.py` joins the result into one timeline per
doctor. That record is the agents' shared memory.

```mermaid
flowchart LR
  crm["CRM"] & mkt["Marketing"] & cc["Contact centre"] & portal["Portal"] --> hook["Signed webhook"]
  batch["Nightly batch<br/>(Temporal schedule)"] --> land
  hook --> land["Land once, idempotent"]
  land --> id["Identity resolution"]
  id -- "known" --> t360[("HCP 360 timeline")]
  id -- "unknown" --> un["Stays unlinked"]
  t360 --> agents["Sentinel, coordinator, insight agent"]
```

### 12. Who contacts the doctor next?

The outreach coordinator checks each planned touch against consent, the country's cap, open medical cases
and whether its content is still current. It holds or proposes, and writes the rule and its reason
(`outreach.py`). When two agents disagree, the supervisor settles it by policy and never by asking a model
(`supervisor.py`, ADR 0023). An open medical case blocks promotion.

```mermaid
sequenceDiagram
  participant M as Marketing plan
  participant O as Outreach coordinator
  participant H as HCP 360
  participant S as Supervisor
  participant L as Ledger
  M->>O: planned email to a doctor
  O->>H: consent, caps, open cases, content currency
  H-->>O: an open medical case on the same product
  O->>S: hold, rule: open case blocks promotion
  S->>L: held, with the rule and the source interactions
  S-->>M: held, reason shown to the rep
```

### 13. A rep's CRM note mentions a rash

The sentinel reads every interaction on every channel, so nobody has to ask it. It opens a pharmacovigilance
case and freezes outreach to that doctor and product, which are both risk-reducing actions and so are
taken alone (`sentinel.py`, ADR 0024).

```mermaid
sequenceDiagram
  participant CRM as CRM
  participant I as Ingest
  participant S as Safety sentinel
  participant PV as Pharmacovigilance queue
  participant O as Outreach
  participant L as Ledger
  CRM->>I: rep note, signed
  I->>S: new interaction
  S->>S: screen, then the model quotes the passage
  S->>PV: SafetySignal with quotes, reporter, date received
  S->>O: freeze contact for this doctor and product
  S->>L: opened, frozen, with the reason
```

### 14. What are doctors raising across channels?

The insight agent clusters what several doctors keep raising. A theme needs at least two doctors and names
its sources but never quotes them, and it is for internal teams only (`insight.py`).

## Act 4: it improves, and proves it

### 15. Self-improvement, proven per release

A **release** pins the prompt versions, the router, the retrieval setup and the policy table, and gets a
hash for an id (`releases.py`, ADR 0025). Every call, trace and case carries its release id. Corrections
become proposals through the improver, which promotes nothing (ADR 0026).

```mermaid
flowchart LR
  corr["Reviewer corrections"] --> imp["Improver"]
  imp --> prop["Proposal: a prompt or router change"]
  prop --> cand["Candidate release"]
  cand --> ev["Eval gate"]
  ev --> safe{"every safety metric holds?"}
  safe -- no --> stop["Blocked"]
  safe -- yes --> base{"quality and cost no worse<br/>than the baseline?"}
  base -- no --> stop
  base -- yes --> human["A person promotes it"]
  human --> live["Live, with monitors by release"]
  live --> corr
```

Safety metrics are absolute: adverse-event recall 1.0, zero ungrounded sentences, zero unsafe automatic
sends, zero calls off the allowlist. Quality and cost are compared with the baseline release. A run that
failed its gate can never be the baseline. The Releases page shows each metric across releases and how live
cases behaved under each.

### 16. The guardian and the traces

The guardian watches budgets, drift and the reviewers' override rate. It trips a country's kill switch or
lowers an agent's autonomy on its own and cannot raise either (`guardian.py`, ADR 0026). `redteam.py`
holds attacks the rule floor must catch whatever a model says. Every case is one trace in OpenTelemetry's
GenAI conventions with personal data redacted, exported to Phoenix locally or Langfuse Cloud when its keys
are set (`tracing.py`, ADR 0027).

```mermaid
sequenceDiagram
  participant G as Guardian
  participant M as Monitors by release
  participant A as Autonomy settings
  participant L as Ledger
  actor Compliance
  M->>G: reviewers rejected 40 percent of drafts in DE
  G->>A: turn automatic replies off for DE
  G->>L: kill switch tripped, with the numbers
  Note over A: every new DE reply now goes to a reviewer
  Compliance->>A: turn it back on, after review
```

### 17. Interfaces for staff and their own agents

The console, `/v1`, MCP and the `hcp` CLI share one front door: one middleware, a verified token, the
tenant from the token and a per-user rate limit (ADR 0028). MCP is a Cedar decision per tool.

```mermaid
sequenceDiagram
  participant H as A client's agent
  participant M as /mcp
  participant A as Middleware
  participant C as Cedar
  participant D as Data
  H->>M: tools/call with a bearer token
  M->>A: verify token, set tenant, count the request
  A->>C: CallMcpTool on this tool name
  C-->>A: ALLOW or DENY
  A->>D: read, tenant-scoped, redacted
  D-->>H: result
```

### 18. Ship it

`deploy/stack.py` is one CDK stack: Aurora Postgres, ElastiCache, Cognito, Verified Permissions, a locked
ledger bucket and a KMS key per tenant, and an ECS Fargate service each for the API and the worker. It
synthesizes with cdk-nag and zero findings, and is never deployed from here (ADR 0029, 0031).

```mermaid
flowchart TB
  subgraph region["One region per data residency"]
    alb["Load balancer"] --> api["ECS: api"]
    api --> pg[("Aurora Postgres")]
    api --> vk[("ElastiCache Valkey")]
    api --> avp["Verified Permissions"]
    worker["ECS: worker"] --> pg
    worker --> tmp["Temporal"]
    api --> s3[("S3 Object Lock, one per tenant")]
    s3 --- kms["KMS key per tenant"]
    cog["Cognito"] --> alb
  end
  api --> bedrock["Anthropic API, or Bedrock"]
```

GitHub Actions runs the gate, SAST, an SBOM, secret scanning and a dependency audit. The harness the
team works in is part of the system too: the Agent SDK options in `agents._options` keep settings,
plugins and slash commands out of a call, the eval harness is `evals.py`, and `.claude/` holds the hooks
and rules that stop a bad edit before it lands.

## Trust boundaries

```mermaid
flowchart LR
  subgraph untrusted["Untrusted"]
    doc["Doctor's message"]
    chan["Channel payloads"]
    mcpc["A client's agents"]
  end
  subgraph edge["Edge: verify and limit"]
    tok["Token check"]
    hmac["HMAC check"]
    rl["Rate limit"]
  end
  subgraph inside["Inside: tenant-scoped"]
    wrap["Message wrapped as data"]
    kern["Kernel and Cedar"]
    dbx[("RLS Postgres")]
  end
  doc --> wrap
  chan --> hmac --> inside
  mcpc --> tok --> rl --> inside
  wrap --> kern --> dbx
```

| Threat | Defence | Test or mutant |
|---|---|---|
| A prompt injection in a message | wrapped as data, rule floor, kernel | red-team corpus |
| A reply with a sentence nobody approved | id-only selection, verify twice | grounding tests, mutants |
| One tenant reads another's rows | token tenant, RLS, Cedar | isolation tests |
| A past entry is edited | hash chain, Object Lock | tamper test |
| A model outside the two allowed | hook, router, gate metric | allowlist tests |
| A signed-in user changes their own role | client cannot write custom attributes | deploy test |

## Module map

| Module | Owns | Tested by |
|---|---|---|
| `world.py` | The synthetic world from `world/*.toml` | `tests/test_world.py` |
| `graph.py`, `kernel.py` | Routing table, engine, policy kernel | `tests/test_graph.py`, `tests/test_kernel.py` |
| `rules.py`, `guards.py` | Keyword screens, label scope, tool guards | `tests/test_rules.py` |
| `agents.py`, `plan.py`, `router.py` | Agent specs, the planning graph, model choice | `tests/test_model_policy.py` |
| `retrieval.py`, `embeddings.py`, `cache.py` | Hybrid retrieval, the embeddings port, the cache | `tests/test_retrieval.py` |
| `grounding.py` | Composing and verifying replies | `tests/test_grounding.py` |
| `cases.py`, `workflows.py`, `activities.py`, `durable.py`, `worker.py` | A case and its durable life | `tests/test_flow.py` |
| `ledger.py`, `privacy.py` | The chain, the archive, erasure | `tests/test_flow.py` |
| `auth.py`, `authz.py`, `db.py`, `store.py` | Identity, permissions, tenancy, storage | `tests/test_auth.py` |
| `gateway.py`, `releases.py`, `evals.py` | Metering, releases, the gate | `tests/test_gateway.py` |
| `ingest.py`, `identity.py`, `hcp360.py` | Channels, identity, the shared memory | `tests/test_ingest.py` |
| `sentinel.py`, `outreach.py`, `supervisor.py`, `insight.py` | Perception and coordination | `tests/test_perception.py` |
| `guardian.py`, `improver.py`, `redteam.py` | Limits and improvement | `tests/test_guardian.py` |
| `tracing.py`, `observe.py` | Traces, metrics, logs | `tests/test_tracing.py` |
| `api.py`, `v1.py`, `mcp_server.py`, `cli.py`, `ratelimit.py` | The interfaces | `tests/test_console.py` |

## Data

| Store | Holds |
|---|---|
| Postgres `documents` | Content, cases, HCPs, touches, proposals: one JSON row each, tenant-scoped by RLS |
| Postgres pgvector index | One vector per approved block, with its model id and dimension |
| Postgres spend log | One row per model call |
| Postgres `eval_runs` | One row per eval run, per release |
| Valkey | Retrieval cache, rate-limit counters, idempotency keys |
| Object Lock bucket | One object per ledger entry, retained ten years |
| Temporal history | Where every running case is |
| Verified Permissions | The Cedar files in `policies/cedar/` |

## Running it

```bash
make up          # Floci, Postgres, Temporal, Valkey, and every resource
make check       # tests, evals, mutants, prose, web build, mermaid
make serve       # console on http://localhost:8765
make walkthrough # recapture docs/product-walkthrough-shots
LIVE=1 uv run python -m hcpagents run inq-101   # one live case
```
