---
name: add-content-block
description: Add or change an approved content block in world/content.toml, keep the world consistent, and see which inquiries it changes. Use when a new approved answer, label change or withdrawal is needed.
---

# Add a content block

1. Add a `[[block]]` to `world/content.toml` with every field: `id`, `product`, `country`, `topic`,
   `version`, `status`, `approved_on`, `expires_on`, `mlr_ref`, `source`, `text`. Ids follow
   `<PRODUCT>-<COUNTRY>-<TOPIC>`. To change approved text, raise `version` and write the new text; never
   edit text under the same version.
2. Write only text that an MLR review would approve. Every sentence ends with a full stop, because
   `grounding.sentences` splits on sentence ends and verifies each sentence on its own.
3. Run `uv run pytest -q tests/test_world.py tests/test_grounding.py`.
4. Run `make provision` to reseed the content table, then `make evals`. Recorded agent selections do not
   know about the new block; an inquiry whose route should change needs `LIVE=1 uv run python -m
   hcpagents run <inquiry-id>` (Haiku 5.5, well under a cent per inquiry), then `make evals` again.
5. If the topic should be answered without a human in a country, that is a Compliance decision in
   `policies/autonomy.toml` (`[auto_send]`), not part of this change.
6. Run `make check`.
