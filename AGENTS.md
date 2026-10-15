# Working on this repository

- Done means `make check` passes. It runs the tests and labs, the eval gate, the mutants, the prose
  check, the web build and the diagram check.
- One model: `claude-haiku-5-5`. `.claude/hooks/haiku_only.py` refuses any other id in code or config, and
  `tests/test_claude_config.py` checks every file.
- `make record` and `LIVE=1` spend money. Everything else replays from `recordings/`.
- A safety property changes only with a test that fails without it and a mutant in `scripts/mutate.py`.
- Copy has no em or en dashes; `scripts/check_prose.py` enforces it.
- Path-scoped rules for the agents and the Cedar policies are in `.claude/rules/`.
