# ADR 0014: LangGraph plans inside one kernel step

Status: accepted, 29 October 2026.

## Context

The assembler was one model call that searched, chose and stopped. A real plan checks its own work. Say a question is still uncovered after the first pass. Then it searches again with other words. It gives up after a set number of tries. That loop needs an explicit graph, not a growing prompt.

## Decision

`plan.py` is a LangGraph `StateGraph` with two nodes. They are `select` (the assembler agent, with its tools)
and `check` (deterministic coverage). One conditional edge loops back to `select` while questions stay
uncovered and attempts remain. It runs entirely inside the kernel's `assemble` step.

- The graph sets no facts and chooses no route. It returns a selection. The grounding verifier and the
  routing table decide what happens next (ADR 0013).
- The loop has two limits. One is the conditional edge. The other is `kernel.check_attempt`. It raises
  `KernelViolation` if a bug in the edge ever lets a third attempt start.
- Ids survive only if a permitted tool call returned them for this product and country.
- No LangGraph checkpointer. One durable record per case is enough. Temporal history will be it (Act 2).

## Consequences

Each attempt is one recorded model call. So a retry is another call that costs a cent or so. Replaying a case replays every attempt from `recordings/`. A new node or edge is a reviewed change to `plan.EDGES`.

## Enforced by

`tests/test_plan.py` checks these. A covered plan stops at one attempt. A gap triggers a named retry. The loop ends at `MAX_ATTEMPTS`. Ids that no tool returned are rejected. Ids from another country are rejected too. The edges of the compiled graph equal `plan.EDGES`. Four mutants in `scripts/mutate.py` remove the bound, the kernel check and each id filter.
