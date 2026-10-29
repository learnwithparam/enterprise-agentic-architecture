# ADR 0018: An always-on steward watches content, and the cache only ever forgets

Status: accepted, 29 October 2026.

## Context

A content block can be withdrawn at any minute. Two things then go stale: drafts waiting on a reviewer
that quote the block, and any cached retrieval answer that contains it. Retrieval is the hot path, so it
needs a cache, but a cache that serves a withdrawn block is an off-label risk.

## Decision

- Retrieval answers are cached in Valkey, keyed by tenant and by everything that shapes the answer
  (question, product, country, topic, k, mode, today, embedding model). Each entry is also listed under
  every block it contains.
- `cases.withdraw` evicts those entries in the same call that withdraws the block, then publishes
  `ContentWithdrawn` carrying the tenant. Eviction does not wait for the queue.
- `ContentStewardWorkflow` is always on, one per platform. Every few seconds an activity drains the queue
  and, for each event in the tenant it names, evicts again (idempotent) and re-verifies every open draft
  that uses the block. It rolls its history over with continue-as-new.
- Valkey is an optimisation. If it is down, reads and writes fall through to Postgres. A failed eviction
  is recorded on the ledger as `cache_evict_failed`, the steward retries it, and the five-minute TTL bounds
  the worst case. Grounding and the send recheck never read the cache.

## Consequences

The steward polls instead of reacting to the queue, which costs a few seconds of delay on draft
invalidation and nothing on cache correctness. A new approval appears in cached answers only after the TTL
or a re-index. Events are deleted when drained, so a crash mid-pass loses them until P3.5 adds a DLQ.

## Enforced by

`tests/test_cache.py`: one test per sentence above, each with a mutant in `scripts/mutate.py`.
