# Prove the audit trail with a hash chain

**The job:** an inspector asks how inquiry inq-105, a reported rash, was handled six months ago. Compliance
must show the route it took, who touched it and that nobody changed the record afterwards, including
someone with database access.

**Before:** an audit table. Anyone who can write to it can change a row, and the changed row looks exactly
like the real one.

**After:** each ledger entry is hashed together with the hash before it (`ledger.digest`), so editing any
past entry breaks the chain at that entry. Every tenth hash is signed with a KMS key, and every entry is
also written to an S3 bucket under Object Lock in compliance mode for ten years. An insider who rewrites
the chain from the edit onwards still cannot forge the signatures or delete the archived copies.

## Run it

```bash
make up
make lab N=prove-the-audit-trail-with-a-hash-chain
```

## Read

- `src/hcpagents/ledger.py`: `digest`, `append`, `verify`, `tamper`, `restore`, `try_delete_archive`.
- `docs/adr/0005-hash-chain-ledger-and-object-lock.md`.
- In the console, `/proof` lets you change a past entry, see the break, restore it and try to delete the archive.

## What the test proves

- An untouched chain verifies, and each hash depends on the one before it.
- Changing a past route from `pv` to `send` breaks the chain at exactly that entry.
- Recomputing that entry's hash only moves the break to the next entry, so a forger has to rewrite every
  later entry, which the signed checkpoints and the locked archive catch.
- On Floci, deleting an archived entry is refused by Object Lock.

## Break it, watch the test fail

In `src/hcpagents/ledger.py`, change `digest` to hash only the entry: replace `(prev + json.dumps(` with
`(json.dumps(` and rerun the lab. "Each hash covers the one before it" fails: entries could now be removed
or reordered without changing any hash. Put it back.

## What production adds

The same code against DynamoDB, KMS and S3 in the client's account, with the archive bucket in a separate
account the platform team cannot administer.
