# ADR 0014: LangGraph plans inside one kernel step

Status: accepted, 29 October 2026.

## Context

The assembler was one model call that searched, chose and stopped. A real plan checks its own work: if a
question is still uncovered after the first pass, search again with other words, and give up after a bounded
number of tries. That loop needs an explicit graph, not a growing prompt.

## Decision

`plan.py` is a LangGraph `StateGraph` with two nodes, `select` (the assembler agent, with its tools) and
`check` (deterministic coverage), and one conditional edge that loops back to `select` while questions stay
uncovered and attempts remain. It runs entirely inside the kernel's `assemble` step.

- The graph sets no facts and chooses no route. It returns a selection; the grounding verifier and the
  routing table decide what happens next (ADR 0013).
- The loop is bounded twice: by the conditional edge and by `kernel.check_attempt`, which raises
  `KernelViolation` if a bug in the edge ever lets a third attempt start.
- Ids survive only if a permitted tool call returned them for this product and country.
- No LangGraph checkpointer. One durable record per case is enough; Temporal history will be it (Act 2).

## Consequences

Each attempt is one recorded model call, so a retry is another cent-scale call. Replaying a case replays
every attempt from `recordings/`. A new node or edge is a reviewed change to `plan.EDGES`.

## Enforced by

`tests/test_plan.py`: a covered plan stops at one attempt, a gap triggers a named retry, the loop ends at
`MAX_ATTEMPTS`, unreturned and cross-country ids are rejected, and the compiled graph's edges equal
`plan.EDGES`. Four mutants in `scripts/mutate.py` remove the bound, the kernel check and each id filter.
