# Ground replies with approved blocks

**The job:** a German dermatologist asks how to dose Veltrona. The reply must say only what Medical, Legal
and Regulatory approved for Germany, in the version that is approved today, and an auditor must be able to
point at any sentence and find its approval number.

**Before:** the model writes the reply from retrieved passages. It reads well, and nobody can prove that
the sentence about food was in the approved text and not written by the model.

**After:** the model picks block ids. `grounding.compose` places those blocks verbatim between fixed
templates, the safety information and the AI disclosure. `grounding.verify` splits the result into
sentences and requires each one to match a sentence in a current approved block for that product and
country. A changed word, a withdrawn block or another country's label fails the check.

## Run it

```bash
make lab N=ground-replies-with-approved-blocks
```

## Read

- `src/hcpagents/grounding.py`: `compose`, `verify` and `required_ids`.
- `world/content.toml` for the synthetic blocks, each with a version, MLR reference and validity dates.
- `docs/adr/0002-model-selects-ids-never-writes.md`.

## What the test proves

- Every sentence of a composed reply carries its block id, version and MLR reference.
- A paraphrase is not evidence, even when it adds one harmless phrase.
- A block withdrawn after the draft was written leaves its sentences untraced, which is why the same check
  runs again at the moment of sending (`cases._send`).
- Another country's label is not evidence for this country's reply.

## Break it, watch the test fail

In `src/hcpagents/grounding.py`, replace `live = [b for b in sources if is_current(b, today)]` with
`live = sources` and rerun the lab. The withdrawn block test fails: a sentence from withdrawn content now
counts as traced. Put the line back. `scripts/mutate.py` makes this same change on every `make check`.

## What production adds

The block store is the client's content management system, read through an adapter that keeps block id,
version and approval reference. The check is the same code.
