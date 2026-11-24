# Ground replies with approved blocks

**The job:** a German dermatologist asks how to dose Veltrona. The reply must say only what Medical, Legal
and Regulatory approved for Germany. It must use the version that is approved today. An auditor must be
able to point at any sentence and find its approval number.

**Before:** the model writes the reply from retrieved passages. It reads well. Nobody can prove that the
sentence about food was in the approved text and not written by the model.

**After:** the model picks block ids. `grounding.compose` places those blocks word for word between fixed
templates, the safety information and the AI disclosure. `grounding.verify` splits the result into
sentences. Each one must match a sentence in a current approved block for that product and country. A changed word, a withdrawn block or another country's label fails the check.

## What you will learn

- Trace each sentence of a reply to its block, version and approval.
- Prove that a withdrawn block stops a reply at the moment of sending.
- Explain why a close rewording is not evidence.

## Prerequisites

[uv](https://docs.astral.sh/uv/) only. No Floci or API key is needed.

## How it works

```mermaid
flowchart LR
    A[Model picks block ids] --> B[Compose places blocks verbatim between templates]
    B --> C[Verify splits the reply into sentences]
    C --> D{Sentence matches a current approved block}
    D -->|yes for this product and country| E[Reply may send]
    D -->|no| F[Reply is refused]
```

## Steps

1. Keep only the blocks for this product and country.
2. List which blocks hold each sentence.
3. Trace each sentence of the reply to a current block.
4. Check each block against the store as it is now.

These are the `# Step` comments in `verify`.

## Run it

```bash
make lab N=ground-replies-with-approved-blocks
```

Expect: 4 passed

## See it in the console

![A reply sent without a human. Each sentence shows the block it came from.](../../docs/product-walkthrough-shots/case-sent-desktop.webp)

A reply sent without a human. Each sentence shows the block it came from.

## Read

- `src/hcpagents/grounding.py`: `compose`, `verify` and `required_ids`.
- `world/content.toml` for the synthetic blocks, each with a version, MLR reference and validity dates.
- `docs/adr/0002-model-selects-ids-never-writes.md`.

## What the test proves

- Every sentence of a composed reply carries its block id, version and MLR reference.
- A paraphrase is not evidence, even when it adds one harmless phrase.
- A block withdrawn after the draft was written leaves its sentences untraced. That is why the same check
  runs again at the moment of sending (`cases._send`).
- Another country's label is not evidence for this country's reply.

## Break it, watch the test fail

In `src/hcpagents/grounding.py`, replace `live = [b for b in sources if is_current(b, today)]` with
`live = sources` and rerun the lab. The withdrawn block test fails: a sentence from withdrawn content now
counts as traced. Put the line back. `scripts/mutate.py` makes this same change on every `make check`.

## What production adds

The block store is the client's content management system. An adapter reads it and keeps the block id,
version and approval reference. The check is the same code.

## Check yourself

<details>
<summary>A block is withdrawn after the draft was written. What happens at send time?</summary>

Its sentences are no longer traced, so the check fails and the reply is not sent.

</details>

<details>
<summary>Can a German reply cite a United States block?</summary>

No. Another country's label is not evidence for this country.

</details>

## Try next

Pick a learner issue. Write the test that fails first, then fix it.

- [#4 Import approved content from a label export](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/4)
- [#12 Fact-check claims instead of exact sentences](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/12)
- [#26 Prove the grounding gate catches a written sentence](https://github.com/learnwithparam/enterprise-agentic-architecture/issues/26)
- [Every open learner issue](https://github.com/learnwithparam/enterprise-agentic-architecture/issues?q=is%3Aopen+label%3Aassignment)

## New words

- **grounding**: Making sure every sentence of a reply comes from approved text.
- **block**: A piece of approved text with an id and a version.
- **verbatim**: Word for word, with no change.
- **MLR**: The Medical, Legal and Regulatory review that approves content.
