# Gate releases with evals

**The job:** an engineer changes the triage prompt to handle Japanese better. The team must check three
things before the change reaches a doctor. Every adverse event must still go to pharmacovigilance. No reply
may go out that a human should have reviewed. No call may use a model outside the allowlist in
`evals/gate.toml`: Haiku 5.5 by default, Sonnet 5.5 where the router allows it.

**Before:** someone tries a few questions in a playground and says it looks fine.

**After:** `evals/gate.toml` is the release contract. `make evals` runs all twenty synthetic inquiries
through the full graph and scores them. `make check` fails on any line that does not hold. Each inquiry
lists its expected route. It also lists the more cautious routes that are safe. So caution passes and risk
does not.

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

## Run it

```bash
make lab N=gate-releases-with-evals   # the gate's logic, no Floci needed
make up && make evals                 # the real gate over every inquiry, in replay, free
```

Expect: 5 passed

Then `make evals` scores all twenty inquiries. Its last two lines are the totals and the verdict.

Expect: 20 cases, route_acceptable 1.0, ae_recall 1.0, then `gate passed`

## Read

- `evals/gate.toml` for the thresholds.
- `src/hcpagents/evals.py`: `score` and `gate`.
- `world/inquiries.toml` for each inquiry's `expect`, `also_safe` and `why`.
- The Release gate section of `/proof` in the console.

## What the test proves

- A run where every case lands on its expected route passes.
- One adverse event routed to a reviewer instead of pharmacovigilance fails the release on recall.
- A more cautious route listed as also safe passes; sending what a human should review fails.
- One call on a model outside the allowlist fails the release.

## Break it, watch the test fail

In `evals/gate.toml`, set `ae_recall = 0.0` and rerun the lab. The missed adverse event test fails: the gate
would now ship a change that drops safety reports. Put it back to `1.0`.

## What production adds

The same gate in CI on every pull request that touches a prompt, a model id, content or a policy, with
`LIVE=1` against Bedrock on a schedule so drift in the model shows up even when the code has not changed.
Per-call traces go to Langfuse for review.

## New words

- **eval**: A test that scores how the system handles sample inquiries.
- **gate**: A check that blocks a release when a score is too low.
- **recall**: The share of real cases that the system caught.
- **allowlist**: The short list of models the system may call.
