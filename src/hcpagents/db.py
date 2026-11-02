"""Postgres, where every row belongs to a tenant and row-level security enforces it.

The app connects as hcp_app, which cannot bypass RLS. Each transaction names its tenant with
set_config('app.tenant_id', ..., true), so the setting ends with the transaction and can never leak
to the next one on the same connection. With no tenant set, every query returns no rows.
Migrations run as the owner, the only place that role is used.
"""

import json
import os
import secrets
from contextlib import contextmanager
from functools import cache
from urllib.parse import quote

import psycopg
from botocore.exceptions import ClientError
from psycopg import sql
from psycopg.rows import dict_row

from hcpagents import world
from hcpagents.aws import client

APP_SECRET = "mi/db/hcp_app"  # Secrets Manager: {username, password, host, port, dbname}; the stack creates the same name


def app_url(parts: dict) -> str:
    """The app role's URL from its secret."""
    q = lambda k: quote(str(parts[k]), safe="")
    return f"postgresql://{q('username')}:{q('password')}@{parts['host']}:{parts['port']}/{parts['dbname']}"


def app_secret(create: bool = False) -> dict:
    """Reads the app role's secret. With create=True a missing one is made with a random password (the local
    emulator; the CDK stack creates it on AWS). There is no environment fallback for the password."""
    sm = client("secretsmanager")
    try:
        return json.loads(sm.get_secret_value(SecretId=APP_SECRET)["SecretString"])
    except ClientError as e:
        if not create or e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    parts = {"username": "hcp_app", "password": secrets.token_urlsafe(24), "host": "localhost", "port": 5433, "dbname": "hcp"}
    sm.create_secret(Name=APP_SECRET, SecretString=json.dumps(parts))
    return parts


@cache
def _app_url() -> str:
    return app_url(app_secret())


def __getattr__(name):  # db.APP_URL is read from Secrets Manager on first use
    if name == "APP_URL":
        return _app_url()
    raise AttributeError(name)


def owner_url(env=os.environ) -> str:
    """The migration role's URL: DATABASE_OWNER_URL, else built from the cluster secret's host, user and password
    (how the ECS migration task receives them), else the local owner."""
    if url := env.get("DATABASE_OWNER_URL"):
        return url
    if all(k in env for k in ("DB_HOST", "DB_OWNER_USER", "DB_OWNER_PASSWORD")):
        return f"postgresql://{quote(env['DB_OWNER_USER'], safe='')}:{quote(env['DB_OWNER_PASSWORD'], safe='')}@{env['DB_HOST']}:5432/hcp"
    return "postgresql://hcp_owner:hcp_owner@localhost:5433/hcp"


OWNER_URL = owner_url()
MIGRATIONS = world.ROOT / "migrations"

DEFAULT_TENANT, current_tenant, as_tenant = world.DEFAULT_TENANT, world.current_tenant, world.as_tenant


@contextmanager
def session():
    """One transaction as the current tenant."""
    with psycopg.connect(_app_url(), row_factory=dict_row) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (current_tenant(),))
        yield conn


def up() -> bool:
    try:
        with psycopg.connect(_app_url(), connect_timeout=2):
            return True
    except (psycopg.Error, ClientError):
        return False


def migrate() -> list[str]:
    """Apply migrations/*.sql in name order, once each, then sync the tenant list. Returns what ran."""
    ran = []
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            with conn.transaction():
                conn.execute(f.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
            ran.append(f.name)
        conn.execute(sql.SQL("ALTER ROLE hcp_app PASSWORD {}").format(sql.Literal(app_secret(create=True)["password"])))
        _app_url.cache_clear()
        for t in world.tenants():
            # The owner is forced through RLS too, so it names the tenant it is writing.
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (t["id"],))
                conn.execute("INSERT INTO tenants (id, name) VALUES (%(id)s, %(name)s) "
                             "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name", t)
    return ran


def wipe() -> None:
    """Delete every document of every tenant. Used by provision --reset."""
    for t in world.tenants():
        with as_tenant(t["id"]), session() as conn:
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM content_index")


if __name__ == "__main__":  # the ECS migration task: python -m hcpagents.db
    print("migrations applied:", ", ".join(migrate()) or "none new")
