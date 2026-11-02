# ADR 0010: Signed ID tokens identify the caller, and the tenant comes from our directory

Status: accepted, 29 October 2026. Supersedes the `X-User` header.

## Context

The API trusted a header that named the user. Anyone who could reach it could be anyone, and nothing tied
a request to a client company. Row-level security (ADR 0009) is only as strong as the tenant it is given.

## Decision

- Callers sign in at `POST /api/login` and receive an ID token signed by the identity provider (Cognito on
  Floci locally, any OIDC issuer in production). Every other `/api` route needs `Authorization: Bearer`.
- `auth.verify` checks the RS256 signature against the issuer's published keys, then issuer, audience (our
  app client), expiry and `token_use=id`. Any failure is a 401 and nothing runs.
- The tenant is read from our own directory (`world/people.toml`), never from a header or a claim the
  caller can shape. The token also carries `custom:tenant`; it must equal the directory's, or the call is a
  403 and nothing runs. The middleware opens `db.as_tenant(...)` before the route runs, so every query is
  scoped to it.
- The library is PyJWT 2.15.1 with `cryptography` for RS256, released 28 September 2026, widely used and
  maintained. Keys are fetched once and cached by the client.

## Options considered

- **Keep a header behind a gateway.** Rejected: the service would trust the network.
- **Opaque session ids.** Rejected: needs a session store and gives agents no portable identity.

## Consequences

Machine callers (agents, the MCP server, the CLI) get tokens from the same provider in later steps. The
demo password is a synthetic local value, overridable with `MI_DEMO_PASSWORD`.

## Enforced by

`tests/test_flow.py`: every `/api` route except login returns 401 for no token, a header-only user, a
nonsense token and a forged one; a token for another audience is refused. Three mutants in
`scripts/mutate.py` drop the bearer requirement, skip the route check, and disable the audience check.
