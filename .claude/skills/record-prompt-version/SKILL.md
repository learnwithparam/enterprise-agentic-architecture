---
name: record-prompt-version
description: Change an agent's system prompt or schema and ship it as a release, re-recording on claude-haiku-5-5 and passing the eval gate. Use for any change to agents.AGENTS.
---

# Record a new prompt version

A prompt change is a release. The eval gate decides whether it ships, on recordings made with the new
prompt.

1. Edit the agent's `system` or `schema` in `src/hcpagents/agents.AGENTS`. Do not change `MODEL`; the
   repository runs on `claude-haiku-5-5` only, and the hook in `.claude/hooks/haiku_only.py` refuses
   any other id.
2. Bump `PROMPT_VERSION` in `src/hcpagents/agents.py` to today's date and a sequence number.
3. `make up`, then `make record`. This calls Haiku 5.5 for every inquiry, about two cents in total, with
   the spend cap in `policies/autonomy.toml` stopping anything larger.
4. `make evals`. If the gate fails, the prompt does not ship. Read `evals/report.json` for the cases that
   moved.
5. Delete recordings no inquiry uses any more: `make evals` rewrites the report, and every recording not
   referenced in it is stale.
6. `make check`, then ask the compliance-reviewer subagent to read the diff.
