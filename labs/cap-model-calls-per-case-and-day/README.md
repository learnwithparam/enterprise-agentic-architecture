# Cap model calls per case and per day

**The job:** two agents that keep handing work to each other, or one case that keeps retrying, can spend a
tenant's money while nobody watches. The cost per case is already capped. This lab caps the count of calls
too, and the count of calls a tenant makes in a day.

**Before:** the only brake is money, and it is checked in one process. A restart forgets it.

**After:** a case may run at most six agent runs and twelve model calls, retries included. A tenant may make
at most 5000 calls a day. The case counts come from the saved case, and the day count is a document in the
tenant's own store, so a new worker sees the same numbers. Past a cap, no call is made. The ledger gets an
entry named `cap_refused` with the reason, and the case goes to a person with the rule `cap_exceeded`.

## Prerequisites

[uv](https://docs.astral.sh/uv/) only. No Floci or API key is needed.

## How it works

```mermaid
flowchart TD
    A[An agent is about to call a model] --> B{Hop cap or call cap reached}
    B -->|yes| R[Ledger entry cap_refused. A person takes the case]
    B -->|no| C{Tenant day cap reached}
    C -->|yes| R
    C -->|no| D[Make the call and add its attempts to today]
```

## Steps

1. Check the hops and the model calls of this one case.
2. Check the tenant's calls today, read from the store.

These are the `# Step` comments in `check`.

## Run it

```bash
make lab N=cap-model-calls-per-case-and-day
```

Expect: 5 passed

## Read

- `src/hcpagents/agent_caps.py`: the three caps, `check` and `charge`.
- `src/hcpagents/case_core.py`: `refuse_over_cap`, which runs before every model call.

## What the test proves

- A case under every cap may call.
- The hop cap, the call cap and the day cap each refuse on their own and name themselves.
- A retry on Sonnet counts as a call.

## Break it, watch the test fail

In `src/hcpagents/agent_caps.py`, change `if calls_today() >= day_cap:` to `if False:`. The day cap test
fails: a tenant could spend with no daily limit. Put it back.

## What production adds

`tests/test_live_g_caps.py` runs a real case. It shows the model is never called after a refusal and that the
kernel turns the refusal into a review with the rule `cap_exceeded`.
