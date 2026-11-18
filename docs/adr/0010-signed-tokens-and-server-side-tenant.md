# ADR 0010: Signed ID tokens identify the caller, and the tenant comes from our directory

Status: accepted, 29 October 2026. Supersedes the `X-User` header.

## Context

The API trusted a header that named the user. Anyone who could reach it could be anyone. Nothing tied a request to a client company. Row-level security (ADR 0009) is only as strong as the tenant it is given.

## Decision

- Callers sign in at `POST /api/login` and receive an ID token signed by the identity provider (Cognito on
  Floci locally, any OIDC issuer in production). Every other `/api` route needs `Authorization: Bearer`.
- `auth.verify` checks the RS256 signature against the issuer's published keys, then issuer, audience (our
  app client), expiry and `token_use=id`. If any check fails, it is a 401 and nothing runs.
- The tenant is read from our own directory (`world/people.toml`), never from a header or a claim the
  caller can shape. The token also carries `custom:tenant`. It must equal the directory's. If not, the call is a
  403 and nothing runs. The middleware opens `db.as_tenant(...)` before the route runs, so every query is
  scoped to it.
- The library is PyJWT 2.15.1 with `cryptography` for RS256, released 28 September 2026, widely used and
  maintained. The client fetches keys once and caches them.

## Options considered

- **Keep a header behind a gateway.** Rejected: the service would trust the network.
- **Opaque session ids.** Rejected: needs a session store and gives agents no portable identity.

## Consequences

Machine callers (agents, the MCP server, the CLI) get tokens from the same provider in later steps. The local demo passwords are random for each user. They live in Secrets Manager under `/mi/users/<id>`. Read one with `uv run python -m hcpagents.auth <user id>`. Password sign-in works only when `MI_ENV` is `local`.

## Enforced by

`tests/test_flow.py` checks these. Every `/api` route except login returns 401 in four cases. They are no token, a header-only user, a nonsense token and a forged one. A token for another audience is refused. Three mutants in `scripts/mutate.py` drop the bearer requirement, skip the route check, and disable the audience check.
