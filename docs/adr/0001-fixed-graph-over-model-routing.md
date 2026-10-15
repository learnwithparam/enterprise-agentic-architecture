# ADR 0001: A fixed graph routes every inquiry, not the model

Status: accepted, 15 October 2026

## Context

An agent that decides its own next step (a planner with subagents, or one model with every tool) is the
default shape for agentic systems. In medical information the route is the regulated decision: an adverse
event must reach pharmacovigilance, an off-label question must reach Medical. A route the model chooses can
change when the prompt, the model or the wording of the question changes, and nobody can show Compliance the
rule that was applied.

## Decision

Seven nodes run in a fixed order (`hcpagents.graph.NODES`). Each establishes facts. After each node the
engine walks a ten-rule routing table (`ROUTING`) in order; the first rule whose fact matches is the route,
and a rule whose fact is not yet known makes the engine wait rather than guess. The same table generates the
Step Functions definition (`asl()`).

## Options considered

- **Model-delegated subagents.** Flexible, and the right shape for open-ended work. Rejected: the route
  would not be reviewable or repeatable.
- **Rules in the prompt.** Rejected: a prompt is not a policy; it cannot be tested for every combination.
- **A fixed graph with a routing table.** Chosen.

## Consequences

The model can be swapped or re-prompted without touching the route. Adding a route is a change to a
reviewed table. The cost: a new kind of inquiry needs a new rule before it can be handled.

## Enforced by

`tests/test_graph.py`: an adverse event always goes to pharmacovigilance, sending needs every safety
fact, an unknown fact waits, every routing fact is set by some node, (each checked over every combination of
facts), and Step Functions on Floci routes like Python for one case per rule plus a pending one.
