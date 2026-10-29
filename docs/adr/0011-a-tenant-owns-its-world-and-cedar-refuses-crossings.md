# ADR 0011: A tenant owns its whole world, and Cedar refuses any crossing

Status: accepted, 29 October 2026.

## Context

Row-level security (ADR 0009) keeps documents apart, and signed tokens (ADR 0010) name the tenant. The
seed data, the people list and the authorization layer still assumed one company.

## Decision

- Each tenant has its own company, products, approved content, HCPs and inbox. Quillon stays in `world/`;
  every other tenant lives in `world/tenants/<id>/`. `world.products()`, `blocks()`, `hcp_world()`,
  `inquiries()` and `people()` answer for the tenant being served, so a caller cannot ask for another's.
- `world/people.toml` is the directory behind sign-in. A person without a `tenant` belongs to Quillon.
- Every Verified Permissions request carries a tenant on the principal (the one it signed in under) and on
  the resource (the one being served). `policies/cedar/tenants.cedar` is a `forbid`, which beats every
  permit, so no other policy can widen access across tenants.

## Consequences

The ledger, autonomy settings and queues are still shared across tenants. They get tenant scoping with the
pseudonymous ledger (crypto-shredding) and the per-tenant gateway keys later in the build.

## Enforced by

`tests/test_flow.py`: a Marlowe user sees none of Quillon's cases, people or HCPs and gets 404 on a Quillon
case; Quillon never sees Marlowe's people; Cedar denies a principal acting across tenants. Two mutants in
`scripts/mutate.py` pin the request to one tenant and weaken the forbid.
