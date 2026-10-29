# Arbitrate agents with a supervisor

**The job:** marketing plans an email, a rep plans a visit and the inquiry agent has a reply ready, all for
the same doctor in the same week. Someone has to decide which goes, and Compliance has to read why.

**Before:** each team sends on its own schedule, or one agent asks another in free text and nobody can
replay the conversation.

**After:** proposals are rows. When two fall within three days of each other the supervisor applies one
rule: a touch that answers the doctor's own need beats a promotional one, then the earlier date wins. The
loser is held, not deleted, and keeps the id of the proposal it yielded to. No model is asked.

## Run it

```bash
make lab N=arbitrate-agents-with-a-supervisor
```

## Read

- `src/hcpagents/supervisor.py`: `arbitrate`.
- `docs/adr/0023-the-coordinator-holds-and-the-supervisor-settles.md` and `docs/adr/0032-agents-talk-through-state-and-events-not-to-each-other.md`.

## What the test proves

- A reply to the doctor beats a campaign, whichever was planned first.
- Between equals the earlier date wins, and far-apart touches do not conflict at all.
- The result does not depend on the order proposals arrive in.

## Break it, watch the test fail

In `src/hcpagents/supervisor.py`, change `bool(p.get("promotional"))` to `False` in `_rank`. The first
test fails: a campaign planned earlier would now silence a doctor's own question. Put it back.

## What production adds

The outreach coordinator feeds the supervisor from the HCP 360 record, an open medical case blocks
promotion outright, and every held touch carries its rule and source interactions on the ledger.
