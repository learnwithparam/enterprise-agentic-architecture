# Pin the model with Agent SDK options

**The job:** the eval gate passed on Claude Haiku 5.5. Production must run that exact model, with that
exact prompt, and nothing from the machine it runs on (a developer's `~/.claude` settings, plugins, MCP
servers or slash commands) may change what the agent can do or which model a background call uses.

**Before:** the Agent SDK starts the Claude Code runtime with whatever settings it finds. A plugin adds a
tool, a settings file switches the small model, and the run that passed the gate is not the run in
production.

**After:** `agents._options` builds every agent's `ClaudeAgentOptions` the same way: `model` pinned,
`setting_sources=[]`, `strict_mcp_config=True`, no plugins, slash commands disabled, built-in tools off,
and the background model environment variables pinned to the same id. Every result is checked for the
models it used, and cost is computed from tokens at Haiku 5.5 prices.

## Run it

```bash
make lab N=pin-the-model-with-agent-sdk-options
```

## Read

- `src/hcpagents/agents.py`: `MODEL`, `PRICE`, `_options`, `check_models`, `recording_key`, `Spend`.
- `docs/adr/0007-haiku-only-and-isolated.md` and `docs/adr/0006-replay-recordings.md`.

## What the test proves

- All three agents run on `claude-haiku-5-5` with no local settings, plugins or stray MCP servers.
- A result that touched any other model is refused, in replay and live.
- Changing a system prompt changes the recording key, so an old recording cannot pass for the new prompt.
- The bill comes from token counts at $0.10 per million input and $0.50 per million output tokens.

## Break it, watch the test fail

In `src/hcpagents/agents.py`, change `setting_sources=[]` to `setting_sources=["user"]` and rerun the
lab. The isolation test fails: the agent would now load your own Claude settings. Put it back.

## What production adds

The same options with `CLAUDE_CODE_USE_BEDROCK=1` and a Bedrock inference profile for Haiku 5.5 in the
client's region. The spend cap per case and per session stays in code, because the runtime's own budget is
a backstop, not the control.
