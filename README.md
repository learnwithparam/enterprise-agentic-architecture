# Enterprise agentic AI architecture

**The job:** answer doctors' product questions for a pharmaceutical company in minutes instead of days,
without ever sending a sentence that Compliance cannot trace to current, approved content, and without
ever missing an adverse event.

Quillon Biopharma is synthetic, and so is every doctor, product and content block. The architecture is
the real one: agents on the Claude Agent SDK, all on `claude-haiku-5-5`, and AWS services running locally
on [Floci](https://floci.io/). The same boto3 code runs against AWS.

| Before | After, in this repository |
|---|---|
| Each question routed by hand between Medical and Legal, taking days | A fixed graph routes each inquiry in one pass; safe, cleared topics are answered at once |
| Nobody can prove a reply was approved content | Every sentence carries its block, version and MLR approval, checked again at the moment of sending |
| An adverse event can sit in a general inbox | Any possible adverse event goes to pharmacovigilance before any other rule; the eval gate fails the release if one is missed |
| Permissions live in application code | Every permission is a Cedar policy in Verified Permissions, including the agents' own tool calls |
| Audit is a log someone could edit | A hash-chained ledger, archived under S3 Object Lock, where any edit is found |

![The inbox: every inquiry with its route and the reason for it](docs/product-walkthrough-shots/inbox-desktop.webp)

## Run it

Needs Docker, [uv](https://docs.astral.sh/uv/) and Node 22.

```bash
make up       # Floci (local AWS) and every resource: DynamoDB, S3, SQS, EventBridge,
              # Step Functions, Cognito, Verified Permissions, SSM, CloudWatch Logs
make serve    # the console on http://localhost:8765
make check    # the gate: tests, labs, evals, mutants, prose, web build, diagrams
```

Model calls replay from `recordings/` by default, so all of the above is free and needs no API key.
`make record` calls Haiku 5.5 for every inquiry, about two cents in total, under the spend cap in
`policies/autonomy.toml`.

## Read it

- [Case study](docs/case-study.md): the platform, agentic AI in a regulated setting, the delivery plan, and
  why this slice.
- [Architecture walkthrough](docs/architecture-walkthrough.md): each part, and the three flows Compliance
  cares about, traced through the code.
- [Product walkthrough](docs/product-walkthrough.md): the console screen by screen, with the moments it
  refuses to answer or act.
- [Delivery plan](docs/delivery-plan.md): from first conversations to a first release in Germany.
- [Architecture decisions](docs/adr/README.md): each one names the failure it prevents and the test that
  enforces it.
- [Labs](labs/README.md): one property per lab, a test that proves it, and a change that breaks it.

## Layout

| Path | What it holds |
|---|---|
| `src/hcpagents/` | The graph, agents, grounding, guards, Cedar client, ledger, API and AWS provisioning |
| `policies/` | Cedar policies and the autonomy settings Compliance controls |
| `world/` | The synthetic company: products, doctors, people, content blocks, inquiries |
| `evals/` | The release gate thresholds and the last report |
| `recordings/` | Recorded Haiku 5.5 calls, keyed on agent, prompt version, model and input |
| `web/` | The Astro console |
| `.claude/` | Rules, a compliance reviewer subagent, skills and a model hook for working on this repository with Claude Code |
