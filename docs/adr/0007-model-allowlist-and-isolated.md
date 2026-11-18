# ADR 0007: Two allowed models, Haiku 5.5 and Sonnet 5.5, in an isolated Agent SDK session

Status: accepted, 29 October 2026. Supersedes the 15 October decision to run on Haiku 5.5 alone.

## Context

The agents began as narrow single-shot jobs. They find quotes, tag questions and pick ids. Haiku 5.5 does those well at a fraction of a cent. Now the system also plans, settles disputes between agents and writes insight digests. Those jobs repay a larger model. By default the Agent SDK loads user and project settings, plugins, MCP servers and slash commands from the machine it runs on. Any of these would change behaviour between a laptop and production.

## Decision

A call may use `claude-haiku-5-5` or `claude-sonnet-5-5` (`agents.ALLOWED_MODELS`) and nothing else. The
model router (ADR 0008) picks one per call. `agents.MODEL` stays Haiku 5.5. It is the default and the
CLI's small-fast model, so the bundled CLI never adds a third. The SDK options set no built-in tools and no
setting sources. They set strict MCP config with only the platform's two tools, no plugins and no slash commands. They also set a
fixed system prompt and JSON schema output. Cost is worked out from tokens at each model's own price
(`agents.PRICES`). A spend cap per case and per session stops live calls. A run that reports usage
from any other model fails.

## Options considered

- **Haiku 5.5 alone.** Rejected: planning and arbitration need more judgment, and a single model leaves
  no escalation step between a cheap pass and a human.
- **Any model the gateway can reach.** Rejected: the eval gate passes on two models, and a third would
  ship one it never saw.
- **SDK defaults.** Rejected: behaviour would depend on the machine.

## Consequences

Adding a model is a reviewed change to `ALLOWED_MODELS`, `PRICES` and the hook's list. It also needs new
recordings and a green gate. One test pins the hook and the code to the same set. We ignore the CLI's own cost
estimate, because it does not know these prices.

## Enforced by

`tests/test_model_policy.py` checks these. The allowlist is exactly the two models, and each has a price. Any other id fails the run. The hook and the code share one set. Options are isolated and pinned. Cost is worked out from tokens at each model's price. The spend cap stops live calls. `tests/test_claude_config.py` checks that the
hook blocks an id off the list, and that every guarded file passes it. The gate threshold
`off_allowlist_calls = 0` holds on every release. A mutant in `scripts/mutate.py` removes the check.
