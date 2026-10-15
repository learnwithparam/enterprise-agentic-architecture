# ADR 0002: The model selects approved block ids and never writes text

Status: accepted, 15 October 2026

## Context

The brief asks for zero hallucination and proof that outbound content is current and approved. A
generated sentence, however good, has no approval reference. Retrieval-augmented generation reduces errors
but still produces sentences nobody approved.

## Decision

The assembler agent returns block ids per question. Code places those blocks verbatim between the
opening template, the safety information, the country's AI disclosure and the closing template
(`grounding.compose`). `grounding.verify` then checks every sentence against the content store as it is now:
each must match a sentence of a current block for this product and country, and the required blocks must be
present.

## Options considered

- **Generate, then check with a second model.** Rejected: two models agreeing is not approval.
- **Generate from retrieved content.** Rejected: the output is still new text.
- **Select ids, compose in code, verify per sentence.** Chosen.

## Consequences

Replies read like standard response letters, not conversation. A question no block covers goes to a
human with no draft. Every sentence sent carries its block, version and MLR reference.

## Enforced by

`tests/test_grounding.py`: one changed word fails, an invented sentence fails, another country's or
product's block is not evidence, an expired block is not evidence, the safety information cannot be left
out, and a block withdrawn after drafting fails at send time.
