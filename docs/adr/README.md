# Architecture decisions

Each decision names the failure it prevents and the test that enforces it.

- [ADR 0001: A fixed graph routes every inquiry, not the model](./0001-fixed-graph-over-model-routing.md)
- [ADR 0002: The model selects approved block ids and never writes text](./0002-model-selects-ids-never-writes.md)
- [ADR 0003: Floci locally, AWS and Bedrock in production](./0003-floci-locally-bedrock-in-production.md)
- [ADR 0004: Verified Permissions with Cedar decides every permission](./0004-cedar-for-every-permission.md)
- [ADR 0005: A hash-chained ledger archived under S3 Object Lock](./0005-hash-chain-ledger-and-object-lock.md)
- [ADR 0006: Replay recorded model calls by default](./0006-replay-recordings.md)
- [ADR 0007: One model, Claude Haiku 5.5, in an isolated Agent SDK session](./0007-haiku-only-and-isolated.md)
