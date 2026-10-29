# ADR 0016: Temporal owns the life of a case

Status: accepted, 29 October 2026.

## Context

A case used to be one coroutine in the API process. If the process died mid-case, the case was lost, and
a reviewer who needs two days had nowhere to wait.

## Decision

- An inquiry is a Temporal workflow (`workflows.py`). It is deterministic and does no I/O: it asks the
  kernel whether each step may run, has an activity run it (`activities.py`), and asks the kernel again
  whether the facts imply a route. The workflow is the only durable record; there is no second store of
  progress (ADR 0014 says the same for LangGraph).
- Each activity rebuilds the case from its document and runs in its tenant, so any worker can run any step.
- The workflow id is `inquiry-<tenant>-<inquiry>`, and asking for a running one joins it, so a double click
  or a retried request never makes two cases.
- An activity refuses any name outside `kernel.ORDER`, so a workflow input cannot reach other methods.
- The API starts workflows and, in development, hosts the worker. In production `MI_WORKER=off` and
  `hcpagents.worker` is its own deployable.
- `cases.run` stays as the in-process driver for evals and tests. A test runs the same inquiries both ways
  and requires the same route, facts, status and ledger entries.

## Consequences

Temporal runs in compose (`temporalio/temporal`, dev server). Steps retry three times; a step that
writes the ledger can repeat its entry until idempotency keys land (P3.5).

## Enforced by

`tests/test_durable.py`: equal results to the in-process run, a replacement worker finishes a case without
repeating a step, a double start joins one workflow, and an unknown step is refused. Two mutants in
`scripts/mutate.py` remove the join and the step guard.
