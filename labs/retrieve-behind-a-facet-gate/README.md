# Retrieve behind a facet gate

**The job:** a German doctor asks about storage. A block that was withdrawn last week quotes the exact
words of the question. It must never be the source of a reply.

**Before:** retrieval ranks everything and filters after. A strong match on withdrawn or foreign content wins.

**After:** product, country, audience, approved status and validity dates are a hard filter in SQL. Ranking
only orders what the gate lets through (ADR 0012). A rep never sees a doctor-only answer. The chatbot sees
only its own script, word for word.

## What you will learn

- Explain why a gate runs before ranking, not after.
- Prove that withdrawn, expired and foreign content is never a candidate.

## Prerequisites

Docker, [uv](https://docs.astral.sh/uv/) and `make up`. The first run downloads the local embedding model,
about 220 MB. No API key.

## How it works

```mermaid
flowchart LR
    Q[Question, product, country] --> G{Facet gate in SQL}
    G -->|tenant, product, country, audience, approved, in date| R[Rank: full text plus vectors]
    G -->|withdrawn, expired, other country| X[Never a candidate]
    R --> T[Top k blocks]
```

## Steps

1. Turn the question into words and a vector.
2. Rank inside the facet gate by text and by vector.
3. Join the two ranks with rank fusion.
4. Keep the best blocks and read them.

These are the `# Step` comments in `_rank`.

## Run it

```bash
make up
make lab N=retrieve-behind-a-facet-gate
```

Expect: `4 passed`

## See it in the console

![Withdraw a content block. From that moment it is never a candidate again.](../../docs/product-walkthrough-shots/withdraw-content-desktop.webp)

Withdraw a content block. From that moment it is never a candidate again.

## Read

- `src/hcpagents/retrieval.py`: the `GATE` constant and `_rank`.
- `src/hcpagents/retrieval_eval.py` for the hybrid versus full text comparison.
- `docs/adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md`.

## What the test proves

- A withdrawn block is never returned, even when the question quotes it word for word.
- Another country's blocks are never returned, whatever the question says.
- Another tenant finds nothing.
- A rep never gets a block marked for doctors only, such as kidney or pregnancy answers.

## Break it, watch the test fail

In `src/hcpagents/retrieval.py`, delete the `AND d.doc ->> 'status' = 'approved'` line from `GATE`. The first
test fails: the withdrawn storage block is back in the results. Put it back.

Then delete the `audience` line from `GATE`. The fourth test fails: the kidney answer reaches the rep.

## What production adds

A re-index on every content change, and a cache that forgets a block the moment it is withdrawn.

## Check yourself

<details>
<summary>A question quotes a withdrawn block word for word. Is the block returned?</summary>

No. The gate removes it before ranking, however well it matches.

</details>

<details>
<summary>A field rep asks about kidney dosing. What do they get?</summary>

No doctors-only block. The audience line in the gate keeps it out.

</details>

## Try next

Pick a learner issue. Write the test that fails first, then fix it.

- [#5 Match the reply language to the doctor](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/5)
- [#6 Prove cross-language retrieval with German queries](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/6)
- [#25 Add hard negatives to the retrieval eval](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/25)
- [Every open learner issue](https://github.com/learnwithparam/enterprise-agentic-architecture/issues?q=is%3Aopen+label%3Aassignment)

## New words

- **facet**: A field you filter on, such as product or country.
- **facet gate**: A hard filter that runs before any ranking.
- **hybrid retrieval**: Search that mixes full text with vectors.
- **embedding**: A list of numbers that stands for the meaning of a text.
