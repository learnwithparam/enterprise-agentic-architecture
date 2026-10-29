# Pick the model with a router

**The job:** Quillon's medical information service makes thousands of cheap calls (screen a message, pick
a block) and a few hard ones (plan a multi-question reply, settle a conflict). Paying for the strong model
on every call wastes money, and using the cheap one for everything misses the hard cases.

**Before:** one model name in a config file. A schema failure retries the same model until the budget is
gone.

**After:** a pure function decides from the task class, the risk, the budget left on the case and what
earlier tries returned. Haiku 5.5 is the default, Sonnet 5.5 takes planning and any failed Haiku try, and
after Sonnet fails or the budget runs out a person takes the case. It can only return one of two ids.

## Run it

```bash
make lab N=pick-the-model-with-a-router
```

## Read

- `src/hcpagents/router.py`: `route`, the task classes and the budget floor.
- `docs/adr/0008-model-router.md` for why the router is a function and the gate runs it whole.

## What the test proves

- Each task class lands on the model the table says, and an unknown class is an error.
- A schema failure escalates exactly once, and a second failure goes to a person.
- A case without budget for a Sonnet call goes to a person instead of spending.
- No input produces a model outside the allowlist.

## Break it, watch the test fail

In `src/hcpagents/router.py`, change `if SONNET in tried:` to `if False:`. The two-failure test fails: a
case would loop on Sonnet forever instead of reaching a person. Put it back.

## What production adds

Every routing decision is traced with its reason, and the AI gateway meters each call by tenant, agent
and release, so the cost of the router itself shows on the Releases page.
