# Bound agent plans with a policy kernel

**The job:** the inquiry agent plans its own steps toward answering a doctor. A planning agent is only
safe to run on a regulated message if some part of the system is not negotiable whatever it plans.

**Before:** the agent calls tools in whatever order the model picks. A plan that skips the adverse-event
screen produces a fluent reply and no safety report.

**After:** agents choose how to do a step; the kernel owns which steps exist, their order, which facts each
may set, and how many cycles a loop may take. Every step is checked before it runs and every route before
it is returned. A violation fails closed to a reviewer, with nothing drafted or sent.

## Run it

```bash
make lab N=bound-agent-plans-with-a-policy-kernel
```

## Read

- `src/hcpagents/kernel.py`: `check_step`, `check_facts`, `check_attempt`, `check_route`, `escalation`.
- `src/hcpagents/graph.py`: the table the kernel derives its order and facts from.
- `docs/adr/0013-a-policy-kernel-bounds-every-plan.md` and `docs/adr/0014-langgraph-inside-one-kernel-step.md`.

## What the test proves

- A step cannot run before the one ahead of it, and an unknown step is refused.
- A step sets exactly the facts it declares, so a late step cannot rewrite the adverse-event fact.
- A planning loop stops at its limit.
- A violation becomes a review route, never a send.

## Break it, watch the test fail

In `src/hcpagents/kernel.py`, delete the `if node != ORDER[len(done)]:` check in `check_step`. The
out-of-order test fails: a plan could now run retrieval before the safety screen. Put it back.

## What production adds

LangGraph runs each agent's reasoning graph inside one kernel step, and a test walks every transition
of the graph through the kernel (`tests/test_kernel.py`).
