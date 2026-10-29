# ADR 0027: One trace per case, redacted, and monitors split by release

Status: accepted, 29 October 2026.

## Context

Reviewers, Compliance and engineers need to see what an agent did and what it cost. Traces that carry a
doctor's name or contact details become a second place personal data lives. Traces without a release
cannot say whether a new release is better on live traffic.

## Decision

- **Standard spans.** `tracing.export_case` replays a finished case as OpenTelemetry spans: a root span
  `case` and a child per step. Model steps carry the GenAI attributes (`gen_ai.system`,
  `gen_ai.request.model`, `gen_ai.usage.*`). Any OTLP backend reads them.
- **Backend by env.** Langfuse Cloud when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set,
  Arize Phoenix when `MI_PHOENIX_URL` is set (`docker compose up phoenix`, port 6006), otherwise no export.
  Tests and the gate never touch the network.
- **Redaction before export.** Emails, phone numbers and the doctor's name parts are replaced, and text is
  cut to 400 characters. Redaction runs on every span input and output.
- **Release on every case.** A case stores `releases.current()`, and the gateway tags spend with the same
  id (`MI_RELEASE` overrides it). `GET /api/monitors` groups live cases by release: route mix, reviewer
  override rate, average cost, p50 and p95 latency.

## Consequences

- Export happens after the case is stored, so a backend outage cannot change a route or block a send.
- Redaction is pattern based. It misses a name the case does not know, so the stored case remains the
  record and traces are for diagnosis only.
- Sampled adverse-event audits and automatic canary comparison are not built; the monitors page gives the
  numbers a human compares.
