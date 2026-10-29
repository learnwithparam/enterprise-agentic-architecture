# ADR 0007: Two allowed models, Haiku 5.5 and Sonnet 5.5, in an isolated Agent SDK session

Status: accepted, 29 October 2026. Supersedes the 15 October decision to run on Haiku 5.5 alone.

## Context

The agents began as narrow single-shot jobs: find quotes, tag questions, pick ids. Haiku 5.5 does those
well at a fraction of a cent. The system now also plans, arbitrates between agents and writes insight
digests, and those jobs repay a larger model. The Agent SDK by default loads user and project settings,
plugins, MCP servers and slash commands from the machine it runs on, any of which would change
behaviour between a laptop and production.

## Decision

A call may use `claude-haiku-5-5` or `claude-sonnet-5-5` (`agents.ALLOWED_MODELS`) and nothing else. The
model router (ADR 0008) picks one per call. `agents.MODEL` stays Haiku 5.5: it is the default and the
CLI's small-fast model, so the bundled CLI never adds a third. The SDK options set no built-in tools, no
setting sources, strict MCP config with only the platform's two tools, no plugins, no slash commands, a
fixed system prompt and JSON schema output. Cost is computed from tokens at each model's own price
(`agents.PRICES`), a spend cap per case and per session stops live calls, and a run that reports usage
from any other model fails.

## Options considered

- **Haiku 5.5 alone.** Rejected: planning and arbitration need more judgment, and a single model leaves
  no escalation step between a cheap pass and a human.
- **Any model the gateway can reach.** Rejected: the eval gate passes on two models, and a third would
  ship one it never saw.
- **SDK defaults.** Rejected: behaviour would depend on the machine.

## Consequences

Adding a model is a reviewed change to `ALLOWED_MODELS`, `PRICES` and the hook's list, plus new
recordings and a green gate. One test pins the hook and the code to the same set. The CLI's own cost
estimate is ignored because it does not know these prices.

## Enforced by

`tests/test_model_policy.py`: the allowlist is exactly the two models and each has a price, any other id
fails the run, the hook and the code share one set, options are isolated and pinned, cost is computed
from tokens at each model's price, and the spend cap stops live calls. `tests/test_claude_config.py`: the
hook blocks an id off the list and every guarded file passes it. The gate threshold
`off_allowlist_calls = 0` holds on every release, and a mutant in `scripts/mutate.py` removes the check.
