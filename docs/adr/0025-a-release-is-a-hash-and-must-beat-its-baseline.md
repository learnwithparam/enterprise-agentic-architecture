# ADR 0025: A release is a hash and must not be worse than its baseline

Status: accepted, 29 October 2026.

## Context

Prompts, the router, the policy kernel and the embedding model all change behaviour. Without a name for
the combination, an eval score and a spend row cannot say which change moved them, and "did this release
improve?" has no answer.

## Decision

- A release id is a hash of a manifest: each agent's prompt and schema, the router constants, the kernel
  table, the model allowlist and the embedding model id. Any change gives a new id. The gateway already tags
  every call with the release, so cost by release comes from `spend_log`.
- Every eval run is stored in `eval_runs` with its manifest, metrics and verdict. Rows are never deleted.
- Safety metrics stay absolute (`[thresholds]`). Quality and cost metrics are also compared with the
  baseline run, with a tolerance per metric in `[regression]` of `evals/gate.toml`. A slip past a tolerance
  fails the gate, so a release that is cheaper but worse, or better but far dearer, is blocked.
- The first passing run becomes the baseline so a fresh checkout gates. After that only `releases.promote`
  moves it, and it refuses a run that failed or regressed. Promotion is a human act.
- `releases.diff` shows each metric's change and which manifest parts differ; `GET /api/releases` shows the
  trend with live cost per release.

## Consequences

- The eval gate needs a database. It already provisions one.
- Eval cases replay recordings, so cost per case reflects the recorded calls, not live prices; the live
  numbers come from the gateway's spend log.
- The `hcp release diff` command and a promote route arrive with the CLI (P5.4); until then promotion is a
  Python call.
