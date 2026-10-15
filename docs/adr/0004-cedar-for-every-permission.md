# ADR 0004: Verified Permissions with Cedar decides every permission

Status: accepted, 15 October 2026

## Context

Who may approve, reject, withdraw content, change autonomy, read case detail, and which tools an agent
may call are compliance decisions. Role checks scattered in application code cannot be read by Compliance
and drift between endpoints.

## Decision

Every human action and every agent tool call asks Amazon Verified Permissions (`hcpagents.authz`). The
policies are five short Cedar files in `policies/cedar/`. The decision and the policy file that made it are
written to the ledger. The application holds no role checks of its own.

## Options considered

- **Role checks in code.** Rejected: not readable by Compliance, not one place.
- **IAM policies.** Rejected: built for AWS resources, not for "a reviewer in Germany approving a German
  case".
- **Cedar in Verified Permissions.** Chosen.

## Consequences

A rule like "nobody approves an AI reply on a pharmacovigilance case" is one `forbid` statement. Agents
are principals too, so an agent cannot read another country's content even if the guard had a bug.

`infra.policy_store` keys the store on a hash of the Cedar files, so an edited policy is the policy in force
after the next provision; without that, a policy change would sit on disk while the old one kept deciding.

## Enforced by

`tests/test_flow.py`: reviewers approve only in their own country, nobody approves on a
pharmacovigilance case, a field rep sees status but not detail, and the API refuses with 403 and the reason.
`tests/test_rules.py` covers the tool guard. `scripts/mutate.py` deletes the country condition and the
pharmacovigilance `forbid` in turn and requires those tests to fail.
