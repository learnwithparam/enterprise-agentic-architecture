# ADR 0002: The model selects approved block ids and never writes text

Status: accepted, 15 October 2026

## Context

The brief asks for zero hallucination. It also asks for proof that outgoing content is current and
approved. A model-written sentence, however good, has no approval ID. Retrieval-augmented generation
cuts errors. But it still makes sentences that nobody approved.

## Decision

The assembler agent returns block ids for each question. Code places those blocks word for word. They go between
the opening template, the safety information, the AI note for the country and the closing template
(`grounding.compose`). Then `grounding.verify` checks every sentence against the content store as it is
now. Each sentence must match a sentence in a current block. That block must be for this product and country.
The required blocks must be there too.

## Options considered

- **Generate, then check with a second model.** Rejected: two models agreeing is not approval.
- **Generate from retrieved content.** Rejected: the output is still new text.
- **Select ids, compose in code, verify per sentence.** Chosen.

## Consequences

Replies read like standard response letters, not like a chat. If no block covers a question, it goes to a human with no draft. Every sentence sent carries its block, version and MLR reference.

## Enforced by

`tests/test_grounding.py` checks these. One changed word fails. An invented sentence fails. A block from
another country or product is not evidence. An expired block is not evidence. The safety information cannot
be left out. A block withdrawn after drafting fails at send time.
