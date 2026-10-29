# ADR 0012: Retrieval ranks inside a hard facet gate, and embeddings are a port

Status: accepted, 29 October 2026.

## Context

Agents found blocks by an exact topic match, so the caller had to guess the topic first. A doctor asking
"what if a patient forgets a tablet?" never says "missed_dose". Ranking by similarity fixes that, but
similarity alone returns the closest text, and the closest text can be an American dose for a German
question, a withdrawn storage rule, or an expired interaction note. In this domain that is an off-label
or unapproved statement.

## Decision

- **The gate comes first.** `retrieval.GATE` is SQL: tenant (row-level security), product, country,
  status approved, and today inside the approval window. Ranking runs only on rows that pass it.
- **Two signals, fused.** Full-text rank (Postgres, OR of the question's words) and vector rank (pgvector,
  cosine) are fused by reciprocal rank fusion. The first is exact on rare words (a dose, a gene name),
  the second matches meaning and other languages.
- **Embeddings are a port.** `embeddings.Embedder` has `model_id`, `dim` and `embed`. The default adapter
  is a local multilingual ONNX model (no key, no network after the first download). A hashing adapter runs
  offline. A hosted adapter is one more class. `MI_EMBEDDINGS` chooses.
- **Models never mix.** Each `content_index` row stores its model id and dimension, and queries filter on
  the active model id, so a new model is built beside the old one and cut over only when the retrieval eval passes.

## Consequences

The column has no fixed dimension, so there is no approximate-nearest-neighbour index; an exact scan is
right for a few thousand blocks per tenant. Past that, one index per model id is the move. The assembler's
`search_approved_content` tool takes a plain-words `query` and calls this retrieval (prompt version 2026-10-29.1).

## Enforced by

`evals/gate.toml [retrieval]` and `python -m hcpagents.retrieval_eval` (in `make check`): on the retrieval
set, hybrid finds the answer in the top 3 for every question, full-text alone does not, and no result
is ever withdrawn, expired or from another country. `tests/test_retrieval.py` covers each gate clause and the
model filter. Four mutants in `scripts/mutate.py` drop a clause each.
