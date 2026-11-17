"""Each user gets a budget of requests for /v1 and /mcp. Valkey keeps the count (ADR 0028).

Each window lasts one minute. It is keyed by tenant and user, so one noisy client cannot starve another.
If Valkey is down, the limit is off. An outage must not lock reviewers out of safety cases.
"""

import os
import time

from hcpagents import cache

LIMIT = int(os.environ.get("MI_RATE_PER_MIN", "120"))
WINDOW_S = 60


def hit(tenant: str, user: str) -> int | None:
    """Count one request. Return the seconds to wait when the user is over the limit, else None."""
    now = int(time.time())
    key = f"rl:{tenant}:{user}:{now // WINDOW_S}"
    try:
        client = cache._client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, WINDOW_S)
    except cache.DOWN:
        return None
    if count > LIMIT:
        return WINDOW_S - now % WINDOW_S
    return None
