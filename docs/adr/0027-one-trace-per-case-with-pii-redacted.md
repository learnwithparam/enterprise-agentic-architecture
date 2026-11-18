# ADR 0027: One trace per case, redacted, and monitors split by release

Status: accepted, 29 October 2026.

## Context

Reviewers, Compliance and engineers need to see what an agent did and what it cost. Traces that carry a doctor's name or contact details become a second place where personal data lives. Traces without a release cannot say whether a new release is better on live traffic.

## Decision

- **Standard spans.** `tracing.export_case` replays a finished case as OpenTelemetry spans. There is a root span
  `case` and a child for each step. Model steps carry the GenAI attributes (`gen_ai.system`,
  `gen_ai.request.model`, `gen_ai.usage.*`). Any OTLP backend reads them.
- **Backend by env.** Langfuse Cloud is used when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set.
  Arize Phoenix is used when `MI_PHOENIX_URL` is set (`docker compose up phoenix`, port 6006). Otherwise there is no export.
  Tests and the gate never touch the network.
- **Redaction before export.** Emails, phone numbers and the doctor's name parts are replaced. Text is
  cut to 400 characters. Redaction runs on every span input and output.
- **Release on every case.** A case stores `releases.current()`. The gateway tags spend with the same
  id (`MI_RELEASE` overrides it). `GET /api/monitors` groups live cases by release. It shows route mix, reviewer
  override rate, average cost, p50 and p95 latency.

## Consequences

- Export happens after the case is stored. So a backend outage cannot change a route or block a send.
- Redaction is pattern based. It misses a name the case does not know. So the stored case remains the
  record. Traces are for diagnosis only.
- Sampled adverse-event audits and automatic canary comparison are not built. The monitors page gives the
  numbers a human compares.
