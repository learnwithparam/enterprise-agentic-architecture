"""The retrieval cache on Valkey (ADR 0018). A cache only ever makes the platform faster, never different.

An entry is keyed by tenant and by everything that shapes the answer. Each entry is also listed under
every block it contains, so withdrawing a block evicts exactly the answers that quote it. If Valkey is
down, reads and writes quietly fall through to Postgres, the source of truth. An eviction that fails
raises, so the caller can record it; the short TTL then bounds how long a stale answer could live.
"""

import functools
import hashlib
import json
import os

import valkey

URL = os.environ.get("MI_VALKEY", "valkey://localhost:6380/0")
TTL_S = 300
DOWN = (valkey.exceptions.ValkeyError, OSError)


class CacheDown(Exception):
    """Valkey could not be reached for an eviction."""


@functools.cache
def _client() -> valkey.Valkey:
    return valkey.Valkey.from_url(URL, socket_timeout=0.5, socket_connect_timeout=0.5)


def key(tenant: str, **shape) -> str:
    """One entry per tenant and per distinct question shape."""
    return f"rc:{tenant}:{hashlib.sha256(json.dumps(shape, sort_keys=True, default=str).encode()).hexdigest()}"


def get(k: str) -> list[dict] | None:
    try:
        raw = _client().get(k)
    except DOWN:
        return None
    return json.loads(raw) if raw else None


def put(tenant: str, k: str, results: list[dict]) -> None:
    try:
        pipe = _client().pipeline()
        pipe.set(k, json.dumps(results), ex=TTL_S)
        for b in results:
            pipe.sadd(_index(tenant, b["block_id"]), k)
            pipe.expire(_index(tenant, b["block_id"]), 2 * TTL_S)
        pipe.execute()
    except DOWN:
        pass


def evict_block(tenant: str, block_id: str) -> int:
    """Drop every cached answer that contains this block. Returns how many entries went."""
    try:
        c = _client()
        keys = c.smembers(_index(tenant, block_id))
        if keys:
            c.delete(*keys)
        c.delete(_index(tenant, block_id))
    except DOWN as e:
        raise CacheDown(str(e)) from e
    return len(keys)


def flush_tenant(tenant: str) -> None:
    """Drop everything cached for a tenant, after its content is re-indexed or reset."""
    try:
        c = _client()
        for pattern in (f"rc:{tenant}:*", f"rb:{tenant}:*"):
            for k in c.scan_iter(match=pattern, count=500):
                c.delete(k)
    except DOWN:
        pass


def _index(tenant: str, block_id: str) -> str:
    return f"rb:{tenant}:{block_id}"
