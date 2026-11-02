# Labs for project 1 of the Agentic AI Buildcamp

Each lab is one property of the platform, a short README with the job it does for Quillon's medical
information service, and a test that proves it. Each README ends with a change that breaks the property, so
you can watch the test fail before you trust it.

```bash
make up                # Floci, for the labs that touch AWS
make lab N=<folder>    # one lab
uv run pytest -q labs  # every lab; make check runs them too
```

| Lab | The property | Needs Floci |
|---|---|---|
| [Route inquiries with a routing table](route-inquiries-with-a-routing-table/) | The order of the rules is the policy; the model never routes | No |
| [Ground replies with approved blocks](ground-replies-with-approved-blocks/) | Every sentence is traced to a current approved block | No |
| [Guard tool calls with Cedar](guard-tool-calls-with-cedar/) | An agent reads only its own case's country and product | Yes |
| [Prove the audit trail with a hash chain](prove-the-audit-trail-with-a-hash-chain/) | An edit to any past entry is found; the archive cannot be deleted | Partly |
| [Gate releases with evals](gate-releases-with-evals/) | One missed adverse event fails the release | No |
| [Pin the model with Agent SDK options](pin-the-model-with-agent-sdk-options/) | An allowlist of two models, nothing loaded from the machine, a bill we compute | No |
| [Pick the model with a router](pick-the-model-with-a-router/) | Haiku by default, Sonnet when asked, then a person | No |
| [Bound agent plans with a policy kernel](bound-agent-plans-with-a-policy-kernel/) | A plan cannot skip a step, rewrite a fact or loop forever | No |
| [Arbitrate agents with a supervisor](arbitrate-agents-with-a-supervisor/) | Policy settles two touches to one doctor, not a model | No |
| [Keep a case alive with Temporal](keep-a-case-alive-with-temporal/) | An overdue review is escalated once and a late decision still lands | Yes, and Temporal |
| [Isolate tenants with row level security](isolate-tenants-with-row-level-security/) | The database, not the code, refuses another tenant's rows | Yes |
| [Retrieve behind a facet gate](retrieve-behind-a-facet-gate/) | Withdrawn, expired and foreign content is never a candidate | Yes |
| [Let the guardian only tighten](let-the-guardian-only-tighten/) | Reviewers' rejections can switch a country off, never on | Yes |
| [Watch with the sentinel and steward](watch-with-the-sentinel-and-steward/) | Safety signals and draft invalidation happen with nobody asking | Yes, and Temporal |

Read `docs/architecture-walkthrough.md` first for how the parts fit together.
