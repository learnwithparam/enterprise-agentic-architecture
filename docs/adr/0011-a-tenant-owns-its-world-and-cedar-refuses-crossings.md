# ADR 0011: A tenant owns its whole world, and Cedar refuses any crossing

Status: accepted, 29 October 2026.

## Context

Row-level security (ADR 0009) keeps documents apart. Signed tokens (ADR 0010) name the tenant. But some parts still assumed one company. These were the seed data, the people list and the permission layer.

## Decision

- Each tenant has its own company, products, approved content, HCPs and inbox. Quillon stays in `world/`.
  Every other tenant lives in `world/tenants/<id>/`. `world.products()`, `blocks()`, `hcp_world()`,
  `inquiries()` and `people()` answer for the tenant being served. So a caller cannot ask for another's.
- `world/people.toml` is the directory behind sign-in. A person without a `tenant` belongs to Quillon.
- Every Verified Permissions request carries a tenant on the principal (the one it signed in under). It also
  carries a tenant on the resource (the one being served). `policies/cedar/tenants.cedar` is a `forbid`.
  A `forbid` beats every permit. So no other policy can widen access across tenants.

## Consequences

The ledger, autonomy settings and queues are still shared across tenants. They get tenant scoping later in the build. That comes with the pseudonymous ledger (crypto-shredding). It also comes with the per-tenant gateway keys.

## Enforced by

`tests/test_flow.py` checks these. A Marlowe user sees none of Quillon's cases, people or HCPs. That user gets 404 on a Quillon case. Quillon never sees Marlowe's people. Cedar denies a principal acting across tenants. Two mutants in `scripts/mutate.py` pin the request to one tenant and weaken the forbid.
