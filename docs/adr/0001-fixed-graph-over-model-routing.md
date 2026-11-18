# ADR 0001: A fixed graph routes every inquiry, not the model

Status: accepted, 15 October 2026

## Context

Most agent systems let the agent pick its own next step. That agent may be a planner with subagents, or one
model with every tool. In medical information the route is the rule the law cares about. An adverse event
must reach pharmacovigilance. An off-label question must reach Medical. A route the model picks can change.
A new prompt, a new model or a new wording of the question can change it. Then nobody can show Compliance the
rule that was used.

## Decision

Seven nodes run in a fixed order (`hcpagents.graph.NODES`). Each node sets facts. After each node the
engine walks a ten-rule routing table (`ROUTING`) in order. The first rule whose fact matches is the route.
If a rule needs a fact that is not known yet, the engine waits. It does not guess. The same table builds the
Step Functions definition (`asl()`).

## Options considered

- **Model-delegated subagents.** Flexible, and the right shape for open-ended work. Rejected: the route
  would not be easy to review or repeat.
- **Rules in the prompt.** Rejected: a prompt is not a policy; it cannot be tested for every combination.
- **A fixed graph with a routing table.** Chosen.

## Consequences

You can swap the model or change its prompt without touching the route. Adding a route is a change to a
reviewed table. The cost is that a new kind of inquiry needs a new rule before it can be handled.

## Enforced by

`tests/test_graph.py` checks these. An adverse event always goes to pharmacovigilance. Sending needs every
safety fact. An unknown fact waits. Some node sets every routing fact. Each of these is checked over every
mix of facts. Step Functions on Floci routes like Python for one case per rule, plus a pending one.
