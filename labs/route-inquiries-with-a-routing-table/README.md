# Route inquiries with a routing table

**The job:** Quillon's medical information service gets questions from doctors on five channels. Each one
must reach the team that owns it: pharmacovigilance for a possible side effect, Medical for an off-label
question, a reviewer for anything not cleared, and the doctor directly only when every check passed.

**Before:** a model decides where a message goes. Nobody can say what it will decide next time, and an
adverse event phrased as a dosing question can be answered instead of reported.

**After:** the agents establish facts (`ae`, `in_scope`, `grounded` and so on) and plain code walks a fixed
table, first match wins. Compliance reads the table; tests walk it.

## Run it

```bash
make lab N=route-inquiries-with-a-routing-table
```

## Read

- `src/hcpagents/graph.py`: `ROUTING`, `decide`, `run` and `asl`.
- `docs/adr/0001-fixed-graph-over-model-routing.md` for why the model never routes.

## What the test proves

- A message that is both an adverse event and an injection attempt goes to pharmacovigilance, because the
  adverse event row comes first.
- Any single fact going wrong keeps the reply from sending.
- The engine returns nothing while a fact it needs is unknown, so a node that has not run cannot be skipped.
- The Step Functions definition is generated from the same table, so production cannot drift from it.

## Break it, watch the test fail

In `src/hcpagents/graph.py`, move the `("injection", True, "decline", ...)` row above the `("ae", ...)` row
and rerun the lab. The adverse event test fails: a side effect wrapped in "ignore your instructions" would
be declined, and the legal report would never be filed. Put the row back.

## What production adds

The same `asl()` output is deployed as the Step Functions state machine, with each node a Lambda task.
`tests/test_graph.py` runs one case per rule through Step Functions on Floci and checks it routes like
Python.
