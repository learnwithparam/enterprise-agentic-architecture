# ADR 0009: Postgres with row-level security holds the documents

Status: accepted, 29 October 2026. Supersedes DynamoDB as the store for cases, content, HCPs and touches.

## Context

The platform serves several client companies. A query that forgets a tenant filter must not leak another client's data. A model call or a new route must not be able to cause that. The next steps also need full-text and vector search over approved content. They need joins across cases and HCPs. They need one transaction per state change. DynamoDB held documents by id. It had no tenant, no search and no joins. The hash-chained ledger keeps DynamoDB and S3 Object Lock. It is append-only and needs no queries.

## Decision

Postgres 17 with the pgvector extension (image `pgvector/pgvector:0.8.1-pg17`, Aurora Postgres in production).

- One `docs` table holds every document with `tenant_id`, `kind`, `id` and `doc jsonb`. A tenant is
  named in `app.tenant_id` through `set_config(..., true)`, which ends with the transaction.
- Every tenant table has `ENABLE` and `FORCE ROW LEVEL SECURITY` and one policy on `app.tenant_id`, with a
  `WITH CHECK` so a write for another tenant is refused.
- The app connects as `hcp_app`, which is not a superuser, cannot bypass RLS and owns nothing. Migrations
  run as the owner. With no tenant set, every query returns no rows.
- The `store` module keeps its old interface, so no caller changed. The driver is `psycopg` 3.3.6, released
  18 September 2026, maintained by the psycopg project.

## Options considered

- **A tenant filter in each query.** Rejected: it is one forgotten `WHERE` away from a leak.
- **A schema or database per tenant.** Rejected: it multiplies migrations and connections for no stronger
  guarantee than RLS gives at this size.
- **Keep DynamoDB and add OpenSearch.** Rejected: two stores to keep consistent, and no joins.

## Consequences

Every new table needs a policy. The structural test fails until it has one. For now, connections open once per transaction. A pool comes with load. A tenant is pinned to a region by running its stack in that region. The CDK step covers this.

## Enforced by

`tests/test_tenancy.py` checks these. Every table forces RLS with a tenant policy. The app role cannot bypass it. A second tenant cannot read or write the first tenant's rows. A write for another tenant is refused. No tenant means no rows. A static test reads the migrations. A mutant in `scripts/mutate.py` removes `FORCE`, and the suite must fail.
