"""A per-user request budget for the machine interfaces (/v1 and /mcp), counted in Valkey (ADR 0028).

Fixed one-minute windows keyed by tenant and user, so one noisy client cannot starve another tenant.
If Valkey is down the limit is not enforced: an outage must not lock reviewers out of safety cases.
"""

import os
import time

from hcpagents import cache

LIMIT = int(os.environ.get("MI_RATE_PER_MIN", "120"))
WINDOW_S = 60


def hit(tenant: str, user: str) -> int | None:
    """Count one request. Returns the seconds to wait when the user is over the limit, else None."""
    now = int(time.time())
    key = f"rl:{tenant}:{user}:{now // WINDOW_S}"
    try:
        client = cache._client()
        n = client.incr(key)
        if n == 1:
            client.expire(key, WINDOW_S)
    except cache.DOWN:
        return None
    return WINDOW_S - now % WINDOW_S if n > LIMIT else None
