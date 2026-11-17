"""Virtual keys and the spend log of the AI gateway. A key stands for a tenant, an agent and a budget."""

import contextlib
import hashlib
import secrets

from hcpagents import db, world
from hcpagents.agents import ALLOWED_MODELS, cost_usd
from hcpagents.aws import client


class Refused(Exception):
    def __init__(self, status: int, kind: str, message: str):
        super().__init__(message)
        self.status, self.kind = status, kind


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue_key(tenant: str, agent: str, budget_usd: float) -> str:
    """A new virtual key. Only its hash is kept."""
    secret = f"vk.{tenant}.{agent}.{secrets.token_urlsafe(24)}"
    with world.as_tenant(tenant), db.session() as conn:
        conn.execute("INSERT INTO virtual_keys (tenant_id, key_hash, agent, budget_usd) VALUES (%s, %s, %s, %s)",
                     (tenant, _hash(secret), agent, budget_usd))
    return secret


def key_for(tenant: str, agent: str) -> str:
    """The key a tenant agent uses. It lives in SSM so all processes share it, and it is made on first use."""
    name = f"/mi/gateway/{tenant}/{agent}"
    with contextlib.suppress(client("ssm").exceptions.ParameterNotFound):
        secret = client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        with world.as_tenant(tenant), db.session() as conn:
            if conn.execute("SELECT 1 FROM virtual_keys WHERE key_hash = %s AND NOT revoked", (_hash(secret),)).fetchone():
                return secret
    secret = issue_key(tenant, agent, world.autonomy_seed()["budget"]["per_session_usd"])
    client("ssm").put_parameter(Name=name, Value=secret, Type="SecureString", Overwrite=True)
    return secret


def revoke(tenant: str, secret: str) -> None:
    with world.as_tenant(tenant), db.session() as conn:
        conn.execute("UPDATE virtual_keys SET revoked = true WHERE key_hash = %s", (_hash(secret),))


def resolve(secret: str) -> dict:
    """The tenant, agent and budget a key stands for, or a refusal.

    The tenant comes from the key. A hash lookup in that tenant proves it, so a fake prefix finds nothing.
    """
    parts = secret.split(".", 3)
    if len(parts) != 4 or parts[0] != "vk":
        raise Refused(401, "authentication_error", "Send a gateway virtual key as x-api-key")
    tenant = parts[1]
    with world.as_tenant(tenant), db.session() as conn:
        row = conn.execute("SELECT agent, budget_usd, revoked FROM virtual_keys WHERE key_hash = %s", (_hash(secret),)).fetchone()
        if row is None or row["revoked"]:
            raise Refused(401, "authentication_error", "Unknown or revoked virtual key")
        spent = conn.execute("SELECT COALESCE(sum(cost_usd), 0) AS s FROM spend_log WHERE key_hash = %s", (_hash(secret),)).fetchone()["s"]
    return {"tenant": tenant, "agent": row["agent"], "hash": _hash(secret), "budget": float(row["budget_usd"]), "spent": float(spent)}


def record(virtual_key: dict, meta: dict, model: str, upstream: str, status: int, usage: dict, latency_ms: int) -> None:
    cost = 0.0
    if model in ALLOWED_MODELS:
        cost = cost_usd(usage, model)
    with world.as_tenant(virtual_key["tenant"]), db.session() as conn:
        conn.execute(
            "INSERT INTO spend_log (tenant_id, key_hash, agent, release, prompt_version, case_id, model, upstream, status, "
            "input_tokens, output_tokens, cache_read, cache_write, cost_usd, latency_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (virtual_key["tenant"], virtual_key["hash"], virtual_key["agent"], meta["release"], meta["prompt_version"],
             meta["case"], model, upstream, status,
             usage.get("input_tokens", 0), usage.get("output_tokens", 0), usage.get("cache_read_input_tokens", 0),
             usage.get("cache_creation_input_tokens", 0), cost, latency_ms))


def spend_by(tenant: str, *columns: str) -> list[dict]:
    """Spend for a tenant by agent, release, prompt version, model or case."""
    allowed = {"agent", "release", "prompt_version", "model", "case_id"}
    assert set(columns) <= allowed, columns
    cols = ", ".join(columns)
    with world.as_tenant(tenant), db.session() as conn:
        return conn.execute(f"SELECT {cols}, count(*) AS calls, sum(cost_usd) AS cost_usd FROM spend_log "
                            f"WHERE status < 400 GROUP BY {cols} ORDER BY {cols}").fetchall()
