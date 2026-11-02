# ADR 0019: One thin gateway meters every model call

Status: accepted, 29 October 2026.

## Context

Finance asks what each tenant costs. A release changes a prompt, and nobody can say whether it got
cheaper or better. A provider has an outage at 2 a.m. All three questions need one place that every
model call passes through.

## Decision

`gateway.py` is a small service of our own that speaks the Anthropic Messages API (`/v1/messages`,
streaming and not). The Agent SDK reaches it by setting `ANTHROPIC_BASE_URL`, so no agent code changes.

- **Virtual keys.** An agent holds `vk.<tenant>.<agent>.<secret>`, never the provider key. Only the
  sha256 of the key is stored, under row-level security. The tenant comes from the prefix and is proved
  by the hash lookup inside that tenant, so a forged prefix finds nothing.
- **Per call checks.** The key (401), the model allowlist, Haiku 5.5 and Sonnet 5.5 only (400), and the
  key's budget (429).
- **Failover.** Upstreams are tried in order on 429, 5xx and connection errors. When all fail the caller
  gets a 502 and the failure is logged.
- **Spend log.** One `spend_log` row per call: tenant, agent, release, prompt version, case, model,
  upstream, status, tokens, cost and latency. The release comes from `MI_RELEASE`; case and prompt
  version travel as `x-mi-*` headers. The release registry (P5.1) reads this table to show whether a
  release improved.
- **Run modes.** Live runs start the gateway inside the process (`gateway.embedded`). Production runs
  it as its own deployable.

## Why not LiteLLM

The plan preferred a LiteLLM proxy, with a thin gateway as the fallback if vetting failed. It failed
on three counts. The newest release was one day old (1.106.6, 2026-10-28). It ships several builds a
day, so a pin goes stale at once. Its container and dependency tree is heavy for a 16 GB laptop that
already runs Postgres, Temporal, Valkey and Floci. We need four features, so the cost of ownership is
about 250 lines and a table.

## Consequences

- Cost per tenant, agent, release and prompt version is one SQL query (`gateway.spend_by`).
- A call that skips the gateway fails: `agents.gateway_env` raises when `MI_GATEWAY` is unset.
- **Bedrock is the second provider** when `MI_BEDROCK_REGION` is set. The gateway translates the Messages
  request to Bedrock Converse and the reply back (including streamed events), and the spend row names the
  upstream that answered. A throttle (429), a 5xx or a timeout moves to the next upstream. Any
  Anthropic-compatible endpoint can still follow (`MI_GATEWAY_FALLBACK_URL`, `MI_GATEWAY_FALLBACK_KEY`).
- Checked live once: four calls on case `inq-101` were logged with agent, release, prompt version and
  case, and their summed cost equalled the case's cost.
- Enforced by `tests/test_gateway.py` and seven mutants in `scripts/mutate.py`.
