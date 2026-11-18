"""A case and a tenant cannot make more model calls than a limit. A refusal is explicit and goes to the ledger.

There are three caps. One case may make at most MAX_CALLS_PER_CASE model calls, retries included. One case may
run at most MAX_HOPS agent runs, so two agents cannot pass work back and forth. One tenant may make at most
TENANT_CALLS_PER_DAY model calls a day. The case counts come from the saved case, so a worker that
takes over after a crash sees the same numbers. The day count is a document in the tenant's own store. It is changed in one statement, so two workers cannot lose a call.
Past a cap, the call is not made and the case goes to a person with the rule cap_exceeded.
"""

from datetime import UTC, datetime

from hcpagents import agents, store

MAX_CALLS_PER_CASE = 12  # The most any one case needs is 10: each agent twice, the assembler twice, and one redraft.
MAX_HOPS = 6  # Safety, triage, the assembler twice and one redraft is 5.
TENANT_CALLS_PER_DAY = 5000
USAGE_TABLE = "mi-usage"


class CapExceeded(agents.EscalateToHuman):
    """A cap stopped the next model call. The case goes to a person."""

    rule = "cap_exceeded"


def calls_made(agent_calls: list[dict]) -> int:
    """Model calls so far in this case. A run that retried on Sonnet made two."""
    return sum(call.get("attempts", 1) for call in agent_calls)


def day_id(moment: datetime | None = None) -> str:
    return "calls-" + (moment or datetime.now(UTC)).strftime("%Y-%m-%d")


def calls_today() -> int:
    row = store.get(USAGE_TABLE, day_id())
    if row is None:
        return 0
    return row["calls"]


def check(agent_calls: list[dict], day_cap: int = TENANT_CALLS_PER_DAY) -> str | None:
    """Why the next call may not start, or None when it may."""
    # Step 1: The hops and the calls of this one case.
    if len(agent_calls) >= MAX_HOPS:
        return f"{len(agent_calls)} agent runs reached the hop cap of {MAX_HOPS}"
    if calls_made(agent_calls) >= MAX_CALLS_PER_CASE:
        return f"{calls_made(agent_calls)} model calls reached the case cap of {MAX_CALLS_PER_CASE}"
    # Step 2: The tenant's calls today, read from the store so a restart cannot hide them.
    if calls_today() >= day_cap:
        return f"the tenant reached its day cap of {day_cap} model calls"
    return None


def reserve(day_cap: int = TENANT_CALLS_PER_DAY) -> str | None:
    """Take one of today's calls before the model is asked. Two workers cannot both take the last one.
    When the day is full the call is given back and the reason is returned."""
    if store.add_to(USAGE_TABLE, day_id(), "calls", 1) > day_cap:
        store.add_to(USAGE_TABLE, day_id(), "calls", -1)
        return f"the tenant reached its day cap of {day_cap} model calls"
    return None


def settle(attempts: int) -> None:
    """Fix today's count once the run is over. One call was taken in reserve, so add the rest.
    A run that made no call at all gives its call back."""
    store.add_to(USAGE_TABLE, day_id(), "calls", attempts - 1)
