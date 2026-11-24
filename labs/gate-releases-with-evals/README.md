# Gate releases with evals

**The job:** an engineer changes the triage prompt to handle Japanese better. The team must check three
things before the change reaches a doctor. Every adverse event must still go to pharmacovigilance. No reply
may go out that a human should have reviewed. No call may use a model outside the allowlist in
`evals/gate.toml`: Haiku 5.5 by default, Sonnet 5.5 where the router allows it.

**Before:** someone tries a few questions in a playground and says it looks fine.

**After:** `evals/gate.toml` is the release contract. `make evals` runs all twenty synthetic inquiries
through the full graph and scores them. `make check` fails on any line that does not hold. Each inquiry lists its expected route and the more cautious routes that are safe. So caution passes and risk
does not.

## What you will learn

- Run the release gate and read its report.
- Prove that one missed adverse event fails a release.

## Prerequisites

[uv](https://docs.astral.sh/uv/) only. No Floci or API key is needed.

## How it works

```mermaid
flowchart LR
    A[Prompt or model change] --> B[make evals runs twenty inquiries]
    B --> C[Each route checked against expect and also safe]
    B --> D[Each model call checked against the allowlist]
    C --> E[Gate compares metrics to gate.toml]
    D --> E
    E --> F[Release passes or fails]
```

## Steps

1. Read the limits from the gate file.
2. A score must not fall below its floor.
3. A count or a cost must not go above its cap.

These are the `# Step` comments in `gate`.

## Run it

```bash
make lab N=gate-releases-with-evals   # the gate's logic, no Floci needed
make up && make evals                 # the real gate over every inquiry, in replay, free
```

Expect: 5 passed

Then `make evals` scores all twenty inquiries. Its last two lines are the totals and the verdict.

Expect: 20 cases, route_acceptable 1.0, ae_recall 1.0, then `gate passed`

## See it in the console

![The release gate. Each case shows the route it should take and the route it took.](../../docs/product-walkthrough-shots/release-gate-desktop.webp)

The release gate. Each case shows the route it should take and the route it took.

## Read

- `evals/gate.toml` for the thresholds.
- `src/hcpagents/evals.py`: `score` and `gate`.
- `world/inquiries.toml` for each inquiry's `expect`, `also_safe` and `why`.
- The Release gate section of `/proof` in the console.

## What the test proves

- A run where every case lands on its expected route passes.
- One adverse event routed to a reviewer instead of pharmacovigilance fails the release on recall.
- A more cautious route listed as also safe passes. Sending what a human should review fails.
- One call on a model outside the allowlist fails the release.

## Break it, watch the test fail

In `evals/gate.toml`, set `ae_recall = 0.0` and rerun the lab. The missed adverse event test fails: the gate
would now ship a change that drops safety reports. Put it back to `1.0`.

## What production adds

The same gate in CI on every pull request that touches a prompt, a model id, content or a policy. A run with `LIVE=1` against Bedrock on a schedule shows drift in the model even when the code has not changed.
Per-call traces go to Langfuse for review.

## Check yourself

<details>
<summary>One adverse event goes to a reviewer, not to pharmacovigilance. Does the release ship?</summary>

No. Adverse event recall must be perfect, so the gate fails.

</details>

<details>
<summary>A case takes a more careful route than expected. Does that fail?</summary>

Not when that route is listed as also safe. Sending what a human should review does fail.

</details>

## Try next

Pick a learner issue. Write the test that fails first, then fix it.

- [#11 Check that a multi-block reply answers the question](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/11)
- [#13 Grow the eval set past twenty cases](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/13)
- [#14 Score red team attacks against the model](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/14)
- [#20 Make the coverage test check the subject](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/20)
- [#22 Gate releases on outreach and fact-check cases](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/22)
- [Every open learner issue](https://github.com/learnwithparam/enterprise-agentic-architecture/issues?q=is%3Aopen+label%3Aassignment)

## New words

- **eval**: A test that scores how the system handles sample inquiries.
- **gate**: A check that blocks a release when a score is too low.
- **recall**: The share of real cases that the system caught.
- **allowlist**: The short list of models the system may call.
