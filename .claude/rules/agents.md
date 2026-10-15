---
paths:
  - "src/hcpagents/agents.py"
  - "src/hcpagents/graph.py"
  - "src/hcpagents/guards.py"
  - "src/hcpagents/grounding.py"
  - "src/hcpagents/cases.py"
---

# Agents, routing and grounding

- The model selects block ids and states facts. It never routes a case and never writes a sentence a
  doctor reads. A change that lets model text reach a reply is refused (ADR 0002).
- A new routing rule is a row in `graph.ROUTING`. Safety rows stay first. Add the fact to `FACTS` and to
  the node that establishes it; `tests/test_graph.py` fails otherwise.
- Any change to an agent's system prompt or schema changes its recording key. Bump `PROMPT_VERSION`, then
  follow `.claude/skills/record-prompt-version`.
- `_options` keeps `setting_sources=[]`, `strict_mcp_config=True`, `plugins=[]` and the pinned env. Do not
  add tools to the safety or triage agents.
- Anything that can stop a send must fail closed: when in doubt, route to review.
- Run `uv run python scripts/mutate.py` after touching any of these files.
