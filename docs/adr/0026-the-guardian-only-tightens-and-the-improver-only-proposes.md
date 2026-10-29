# ADR 0026: The guardian only tightens and the improver only proposes

Status: accepted, 29 October 2026.

## Context

An always-on system needs something watching its own limits, and something turning reviewer corrections
into change. Both are powers: one that can raise autonomy, or promote its own work, defeats the control
plane. The rule from the roster is that an agent acts alone only in the direction that reduces risk.

## Decision

- **Guardian.** It counts reviewed AI drafts per country from the ledger (approved and rejected). When at
  least `min_decisions` have been reviewed and the rejected share is above `max_override_rate`
  (`policies/autonomy.toml`, `[guardian]`), it switches that country's automatic replies off and writes a
  `guardian_lowered` ledger entry. It has no code path that sets `enabled` to true. A human raises it with
  `cases.set_autonomy` (Cedar checked), and the count restarts from that change, so old rejections do not
  trip it again.
- **Improver.** A rejected AI draft is kept as a correction (country, product, topics, no text). A topic
  corrected at least twice in a country becomes one `stop_auto_send` proposal with status `proposed`. It
  edits no policy, no prompt and no release. A human accepts a proposal, and the release gate (ADR 0025)
  shows whether the change helped.
- **Red-team corpus.** `evals/redteam.toml` lists injection and hidden-safety attacks. The rule screens must
  catch every one, and `redteam_misses = 0` is a threshold in the eval gate, so a screen change that lets
  one through blocks the release.

## Consequences

- Autonomy settings are still one SSM parameter per country, shared by tenants, so a guardian lowering in
  one tenant lowers it for both. Per-tenant parameters are future work.
- The improver proposes a policy change, not a new prompt. Having Sonnet draft candidate prompts is left
  out; the manifest and the gate are ready for it.
- Shadow and canary rollout flags are not built here. Per-release online monitors arrive with tracing (P5.3).
