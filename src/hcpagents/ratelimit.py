"""Each user gets a budget of requests for /v1 and /mcp. Valkey keeps the count (ADR 0028).

Each window lasts one minute. It is keyed by tenant and user, so one noisy client cannot starve another.
If Valkey is down, the limit is off. An outage must not lock reviewers out of safety cases.
"""

import math
import os
import time
from collections import deque

from fastapi import HTTPException, Request

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


class SlidingWindow:
    """Remember when each key last called. Allow `limit` calls in any `window_s` seconds, kept in this process."""

    def __init__(self, limit: int, window_s: float = WINDOW_S, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self.calls: dict[str, deque] = {}

    def hit(self, key: str) -> int | None:
        """Count one call. Return the whole seconds to wait when the key is over the limit, else None."""
        now = self.clock()
        recent = self.calls.setdefault(key, deque())
        while recent and recent[0] <= now - self.window_s:
            recent.popleft()
        if len(recent) < self.limit:
            recent.append(now)
            return None
        if not recent:
            return int(self.window_s)
        return max(1, math.ceil(recent[0] + self.window_s - now))


def caller_address(request: Request) -> str:
    """The load balancer adds the real caller as the last X-Forwarded-For entry. Earlier entries can be forged."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def by_caller(limit: int):
    """A FastAPI dependency that answers 429 when one address calls too often. Use it on routes with no token."""
    window = SlidingWindow(limit)

    def check(request: Request) -> None:
        wait = window.hit(caller_address(request))
        if wait:
            raise HTTPException(429, "Too many requests", headers={"Retry-After": str(wait)})

    check.window = window
    return check


LOGIN = by_caller(int(os.environ.get("MI_LOGIN_PER_MIN", "10")))
HOOKS = by_caller(int(os.environ.get("MI_HOOK_PER_MIN", "600")))
