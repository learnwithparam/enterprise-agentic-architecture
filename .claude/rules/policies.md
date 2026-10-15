---
paths:
  - "policies/cedar/**"
  - "src/hcpagents/authz.py"
---

# Cedar policies

- Every permission is a Cedar statement here; the application holds no role checks (ADR 0004).
- Prefer a `forbid` for a rule that must never be overridden, such as approval on a pharmacovigilance case.
- A changed `.cedar` file takes effect at the next `make provision`, because the policy store is keyed on
  the hash of these files.
- Every policy change needs a test in `tests/test_flow.py` that fails without it, and a mutant in
  `scripts/mutate.py` that removes it.
- Ask the compliance-reviewer subagent to read the diff before committing.
