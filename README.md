# Build an agentic AI system for a regulated company

Project 1 of the Agentic AI Buildcamp for Engineers & PMs. Four 10-minute sessions, each with a lab you run
and a test that proves the property.

| Session | What you build | Labs |
|---|---|---|
| 1. Design a Regulated AI Workflow | The outcome, the metric and the must nevers, then a routing table with safety first | [Route inquiries](labs/route-inquiries-with-a-routing-table/) |
| 2. Build Grounded Agent Replies | Pinned agents that select approved block ids, and a check on every sentence | [Ground replies](labs/ground-replies-with-approved-blocks/), [Pin the model](labs/pin-the-model-with-agent-sdk-options/) |
| 3. Secure Agent Tool Calls with Cedar | A Cedar check on every tool call, and an audit trail nobody can edit | [Guard tool calls](labs/guard-tool-calls-with-cedar/), [Hash chain](labs/prove-the-audit-trail-with-a-hash-chain/) |
| 4. Prove Every Release with an Eval Gate | Twenty eval cases, a gate that fails on one missed adverse event, and mutants | [Gate releases](labs/gate-releases-with-evals/) |

**The job:** answer doctors' product questions for a pharmaceutical company in minutes instead of days,
without ever sending a sentence that Compliance cannot trace to current, approved content, and without
ever missing an adverse event.

Quillon Biopharma is synthetic, and so is every doctor, product and content block. The architecture is
the real one: agents on the Claude Agent SDK, on `claude-haiku-5-5` or `claude-sonnet-5-5`, and AWS services running locally
on [Floci](https://floci.io/). The same boto3 code runs against AWS.

| Before | After, in this repository |
|---|---|
| Each question routed by hand between Medical and Legal, taking days | Eight agents with goals and limits plan their own steps under a policy kernel; safe, cleared topics are answered at once |
| Nobody can prove a reply was approved content | Every sentence carries its block, version and MLR approval, checked again at the moment of sending |
| An adverse event can sit in a general inbox | Any possible adverse event goes to pharmacovigilance before any other rule; the eval gate fails the release if one is missed |
| Permissions live in application code | Every permission is a Cedar policy in Verified Permissions, including the agents' own tool calls |
| Audit is a log someone could edit | A hash-chained ledger, archived under S3 Object Lock, where any edit is found |

![The inbox: every inquiry with its route and the reason for it](docs/product-walkthrough-shots/inbox-desktop.webp)

## Run it

Needs Docker, [uv](https://docs.astral.sh/uv/) and Node 22. The first run downloads the local embedding model
(about 220 MB). What Floci covers, and what it does not, is in [docs/floci-support.md](docs/floci-support.md).

```bash
make up       # Postgres with pgvector, and Floci (local AWS) with every resource: DynamoDB, S3, KMS, SQS,
              # EventBridge, Step Functions, Cognito, Verified Permissions, SSM, CloudWatch Logs
make serve    # the console on http://localhost:8765
make check    # the gate: tests, labs, evals, mutants, prose, web build, diagrams
```

Replay needs no key: model calls replay from `recordings/` by default, so all of the above is free.
`make record` and `make serve LIVE=1` need `ANTHROPIC_API_KEY`. For live calls copy `.env.example` to a file named `.env` (git ignores it) and set `ANTHROPIC_API_KEY`,
then run `make serve LIVE=1`. The repo reads that file into its own process only; nothing sources it.
`make record` calls Haiku 5.5 for every inquiry, about two cents in total, under the spend cap in
`policies/autonomy.toml`.

## Read it

The four sessions teach the build. These pages are the reading around it, and a PM starts with the
case study and the delivery plan.

- [Case study](docs/case-study.md): the platform, agentic AI in a regulated setting, the delivery plan, and
  why this slice.
- [Architecture walkthrough](docs/architecture-walkthrough.md): each part, and the three flows Compliance
  cares about, traced through the code.
- [Product walkthrough](docs/product-walkthrough.md): the console screen by screen, with the moments it
  refuses to answer or act.
- [Coverage](docs/coverage.md): every ask in the case study, every role requirement and every agentic concept,
  with the doc, screen, lab and test for each, checked by `tests/test_coverage.py`.
- [Validation pack](docs/validation-pack.md): a GAMP 5 style map from each requirement to its test and mutant.
- [EU AI Act classification](docs/eu-ai-act.md): where each agent falls and which control meets each duty.
- [Delivery plan](docs/delivery-plan.md): from first conversations to a first release in Germany.
- [Architecture decisions](docs/adr/README.md): each one names the failure it prevents and the test that
  enforces it.
- [Labs](labs/README.md): one property per lab, a test that proves it, and a change that breaks it.

## Layout

| Path | What it holds |
|---|---|
| `src/hcpagents/` | The policy kernel, agents, grounding, guards, Cedar client, ledger, API and AWS provisioning |
| `policies/` | Cedar policies and the autonomy settings Compliance controls |
| `world/` | The synthetic company: products, doctors, people, content blocks, inquiries |
| `evals/` | The release gate thresholds and the last report |
| `recordings/` | Recorded Haiku 5.5 calls, keyed on agent, prompt version, model and input |
| `web/` | The Next.js console |
| `.claude/` | Rules, a compliance reviewer subagent, skills and a model hook for working on this repository with Claude Code |
