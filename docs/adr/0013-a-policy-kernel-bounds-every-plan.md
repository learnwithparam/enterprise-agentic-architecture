# ADR 0013: A policy kernel bounds every plan

Status: accepted, 29 October 2026.

## Context

The routing table (`graph.ROUTING`) was safe while a fixed sequence of nodes walked it. Agents that plan
their own steps (ADR 0014 onward) can reorder, repeat or skip steps, or return facts they were not asked
for. If the safety of a case depended on every agent behaving, one bad plan could draft an answer after an
adverse event.

## Decision

`kernel.py` owns the invariants and checks them in code the agents cannot edit:

- Steps run in `graph.NODES` order, each once. The safety screen cannot be skipped.
- After a route is decided no further step runs.
- A step sets exactly the facts it is declared to produce, so a late step cannot rewrite `ae`.
- A route is valid only if `graph.decide` implies it.

Agents choose how to do a step (which tool, how many retrieval tries). The kernel chooses which steps exist.
A violation fails closed: the case goes to a human reviewer with the rule `kernel_violation` and nothing is
drafted or sent.

## Consequences

Plans are free inside a step and fixed between steps. A plan that needs a new step needs a reviewed row in
`graph.NODES`, not a prompt change.

## Enforced by

`tests/test_kernel.py` drives misbehaving nodes through `kernel.run` and a case whose plan breaks the
kernel. Four mutants in `scripts/mutate.py` remove one check each.
