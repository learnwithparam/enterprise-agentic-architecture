"""The list of revoked users (concept 39). A revoked user stops working on the next call.

A signed token stays good until it ends. So we also keep a list of revoked users in Valkey.
The API reads that list on every call, once the token is proved and before any data is read.
If the list cannot be read, the call is refused. A revoked person must never get in because a cache was down.
The function revoke_user in auth adds a person here and also tells the identity provider.
"""

from hcpagents import cache


class Revoked(Exception):
    """The user was revoked, or we could not check."""


def _name(tenant: str, user_id: str) -> str:
    return f"revoked:{tenant}:{user_id}"


def add(tenant: str, user_id: str) -> None:
    cache._client().set(_name(tenant, user_id), "1")


def remove(tenant: str, user_id: str) -> None:
    cache._client().delete(_name(tenant, user_id))


def check(tenant: str, user_id: str) -> None:
    """Raise Revoked when the user is on the list. Raise it too when the list cannot be read."""
    try:
        listed = cache._client().exists(_name(tenant, user_id))
    except cache.DOWN as error:
        raise Revoked("Cannot check access right now. Try again") from error
    if listed:
        raise Revoked("Access was revoked")
