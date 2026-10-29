# ADR 0028: The /v1 API, MCP and the CLI share one front door

Status: accepted, 29 October 2026.

## Context

Staff use the console. A client's own systems, scripts and agents need the platform too. Each extra
interface is another way to skip authentication, tenancy or a limit if it brings its own checks.

## Decision

- **One middleware.** `/api`, `/v1` and `/mcp` all pass `verified_token_on_every_api_call`: a verified
  bearer token, the tenant set from the token, and for `/v1` and `/mcp` a per-user request budget.
- **/v1 is the contract.** `/api` follows the console and may change with it. `/v1` is read and operate
  only: cases, a server-sent-events stream per case, dead letters with replay, release trend, diff and
  promote. Replay and promote are Cedar actions for compliance (`compliance.cedar`).
- **Rate limit.** `ratelimit.hit` counts requests per tenant and user in one-minute windows in Valkey and
  answers 429 with `Retry-After`. If Valkey is down the limit is not enforced, so an outage cannot lock
  reviewers out of safety cases.
- **MCP is a policy decision per tool.** Tools are served over stateless streamable HTTP. Each tool asks
  Cedar for `CallMcpTool` on its name (`interfaces.cedar`): field representatives get none, and tools
  marked sensitive are for compliance. Tenant and redaction come from the same code as `/v1`.
- **The CLI is a client.** `hcp` calls `/v1` with a token kept in a 0600 file. It has no logic of its own.

## Consequences

- A new interface is one more prefix in `PROTECTED`. A structural test walks every `/api` and `/v1`
  route without a token, and a mutant drops `/v1` from the list.
- The sign-in is a password exchange against the identity provider, not an OAuth device flow. The MCP
  server accepts the same bearer token and does not host an OAuth authorization server.
- MCP in stateless mode keeps no session, so no server-initiated messages. The tools are request and reply.
- Each app lifespan builds its own MCP server, because the SDK runs a session manager once.
