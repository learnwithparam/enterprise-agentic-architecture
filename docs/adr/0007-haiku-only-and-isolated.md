# ADR 0007: One model, Claude Haiku 5.5, in an isolated Agent SDK session

Status: accepted, 15 October 2026

## Context

Each agent does one narrow job: find quotes, tag questions, pick ids. A larger model costs more and adds
nothing to these jobs. The Agent SDK by default loads user and project settings, plugins, MCP servers and
slash commands from the machine it runs on, any of which would change behaviour between a laptop and
production.

## Decision

Every agent runs on `claude-haiku-5-5` (`agents.MODEL`). The SDK options set no built-in tools, no
setting sources, strict MCP config with only the platform's two tools, no plugins, no slash commands, a
fixed system prompt and JSON schema output. Cost is computed from tokens at Haiku 5.5 prices, a spend cap
per case and per session stops live calls, and a run that reports usage from any other model fails.

## Options considered

- **A larger model for the assembler.** Rejected: the eval gate passes on Haiku 5.5 at under a fifth of a
  cent per case.
- **SDK defaults.** Rejected: behaviour would depend on the machine.

## Consequences

A model change is a reviewed change to one constant plus new recordings and a green gate. The CLI's own
cost estimate is ignored because it does not know this model's price.

## Enforced by

`tests/test_model_policy.py`: another model fails the run, options are isolated and pinned, cost is
computed from tokens at Haiku 5.5 prices, and the spend cap stops live calls. The gate threshold
`non_haiku_calls = 0` holds on every release.
