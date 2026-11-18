# ADR 0004: Verified Permissions with Cedar decides every permission

Status: accepted, 15 October 2026

## Context

Some choices are compliance decisions. Who may approve, reject or withdraw content is one. Who may change autonomy or read case detail is another. Which tools an agent may call is a third. Role checks spread through app code cannot be read by Compliance. They also drift apart between endpoints.

## Decision

Every human action and every agent tool call asks Amazon Verified Permissions (`hcpagents.authz`). The
policies are five short Cedar files in `policies/cedar/`. The decision and the policy file that made it go
to the ledger. The app holds no role checks of its own.

## Options considered

- **Role checks in code.** Rejected: not readable by Compliance, not one place.
- **IAM policies.** Rejected: built for AWS resources, not for "a reviewer in Germany approving a German
  case".
- **Cedar in Verified Permissions.** Chosen.

## Consequences

A rule like "nobody approves an AI reply on a pharmacovigilance case" is one `forbid` statement. Agents
are principals too. So an agent cannot read another country's content. This holds even if the guard had a bug.
`infra.policy_store` keys the store on a hash of the Cedar files. So an edited policy is the policy in force
after the next provision. Without that, a policy change would sit on disk. The old one would keep deciding.

## Enforced by

`tests/test_flow.py` checks these. Reviewers approve only in their own country. Nobody approves on a
pharmacovigilance case. A field rep sees status but not detail. The API refuses with 403 and the reason.
`tests/test_rules.py` covers the tool guard. `scripts/mutate.py` deletes the country condition and the
pharmacovigilance `forbid` in turn. It requires those tests to fail.
