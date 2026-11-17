"""The cache for search results, on Valkey (ADR 0018). A cache only makes the platform faster, never different.

A key holds the tenant and all that shapes the answer. Each entry is also listed under each block in it.
So withdrawing a block clears just the answers that quote it.

If Valkey is down, reads and writes quietly fall through to Postgres, the source of truth.
An eviction that fails raises, so the caller can record it. The short TTL then limits how long a stale answer could live.
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


def get(entry_key: str) -> list[dict] | None:
    try:
        raw = _client().get(entry_key)
    except DOWN:
        return None
    if not raw:
        return None
    return json.loads(raw)


def put(tenant: str, entry_key: str, results: list[dict]) -> None:
    try:
        pipe = _client().pipeline()
        pipe.set(entry_key, json.dumps(results), ex=TTL_S)
        for block in results:
            pipe.sadd(_index(tenant, block["block_id"]), entry_key)
            pipe.expire(_index(tenant, block["block_id"]), 2 * TTL_S)
        pipe.execute()
    except DOWN:
        pass


def evict_block(tenant: str, block_id: str) -> int:
    """Drop each cached answer that has this block. Gives back how many went."""
    try:
        connection = _client()
        keys = connection.smembers(_index(tenant, block_id))
        if keys:
            connection.delete(*keys)
        connection.delete(_index(tenant, block_id))
    except DOWN as error:
        raise CacheDown(str(error)) from error
    return len(keys)


def flush_tenant(tenant: str) -> None:
    """Drop all that is cached for a tenant after its content changes."""
    try:
        connection = _client()
        for pattern in (f"rc:{tenant}:*", f"rb:{tenant}:*"):
            for entry_key in connection.scan_iter(match=pattern, count=500):
                connection.delete(entry_key)
    except DOWN:
        pass


def _index(tenant: str, block_id: str) -> str:
    return f"rb:{tenant}:{block_id}"
