# ADR 0028: The /v1 API, MCP and the CLI share one front door

Status: accepted, 29 October 2026.

## Context

Staff use the console. A client's own systems, scripts and agents need the platform too. Each extra interface can skip authentication, tenancy or a limit. That happens if it brings its own checks.

## Decision

- **One middleware.** `/api`, `/v1` and `/mcp` all pass `verified_token_on_every_api_call`. It needs a verified
  bearer token. It sets the tenant from the token. For `/v1` and `/mcp` it also applies a per-user request budget.
- **/v1 is the contract.** `/api` follows the console and may change with it. `/v1` is read and operate
  only. It has cases, a server-sent-events stream per case, dead letters with replay, release trend, diff and
  promote. Replay and promote are Cedar actions for compliance (`compliance.cedar`).
- **Rate limit.** `ratelimit.hit` counts requests per tenant and user in one-minute windows in Valkey. It
  answers 429 with `Retry-After`. If Valkey is down, the limit is not enforced. So an outage cannot lock
  reviewers out of safety cases.
- **MCP is a policy decision per tool.** Tools are served over stateless streamable HTTP. Each tool asks
  Cedar for `CallMcpTool` on its name (`interfaces.cedar`). Field representatives get none. Tools
  marked sensitive are for compliance. Tenant and redaction come from the same code as `/v1`.
- **The CLI is a client.** `hcp` calls `/v1` with a token kept in a 0600 file. It has no logic of its own.

## Consequences

- A new interface is one more prefix in `PROTECTED`. A structural test walks every `/api` and `/v1`
  route without a token. A mutant drops `/v1` from the list.
- The `hcp` CLI signs in with the OAuth authorization code flow and PKCE against a loopback redirect. So the
  person types their password into the identity provider's page. The CLI never sees it. Cognito has no
  device-code grant, here or on AWS. `/.well-known/oauth-protected-resource` (RFC 9728) names the issuer, and
  a 401 points at it. The console and the approver's re-sign-in (ADR 0017) still use the server-side password
  exchange. The MCP server accepts the same bearer token. It does not host an authorization server.
- MCP in stateless mode keeps no session. So there are no server-initiated messages. The tools are request and reply.
- Each app lifespan builds its own MCP server, because the SDK runs a session manager once.
