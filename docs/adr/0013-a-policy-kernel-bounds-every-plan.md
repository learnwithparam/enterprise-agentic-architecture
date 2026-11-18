# ADR 0013: A policy kernel bounds every plan

Status: accepted, 29 October 2026.

## Context

The routing table (`graph.ROUTING`) was safe while a fixed sequence of nodes walked it. Agents that plan their own steps (ADR 0014 onward) can reorder, repeat or skip steps. They can also return facts they were not asked for. If a case was safe only when every agent behaved, one bad plan could draft an answer after an adverse event.

## Decision

`kernel.py` owns the invariants. It checks them in code that the agents cannot edit.

- Steps run in `graph.NODES` order, each once. The safety screen cannot be skipped.
- After a route is decided no further step runs.
- A step sets exactly the facts it is declared to produce, so a late step cannot rewrite `ae`.
- A route is valid only if `graph.decide` implies it.

Agents choose how to do a step (which tool, how many retrieval tries). The kernel chooses which steps exist.
A violation fails closed. The case goes to a human reviewer with the rule `kernel_violation`. Nothing is
drafted or sent.

## Consequences

Plans are free inside a step and fixed between steps. A plan that needs a new step needs a reviewed row in `graph.NODES`. A prompt change is not enough.

## Enforced by

`tests/test_kernel.py` drives misbehaving nodes through `kernel.run`. It also drives a case whose plan breaks the kernel. Four mutants in `scripts/mutate.py` remove one check each.
