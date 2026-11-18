"""Postgres, where each row has a tenant. Row-level security keeps the tenants apart.

The app connects as hcp_app, which cannot bypass RLS. Each transaction names its tenant with
set_config('app.tenant_id', ..., true). The setting ends with the transaction, so it never leaks
to the next one on the same connection. With no tenant set, every query returns no rows.
Migrations run as the owner. That is the only place the role is used.
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

APP_SECRET = "mi/db/hcp_app"  # a Secrets Manager name; the stack makes the same one


def app_url(parts: dict) -> str:
    """The app role's URL from its secret."""
    username, password = (quote(str(parts[key]), safe="") for key in ("username", "password"))
    return f"postgresql://{username}:{password}@{parts['host']}:{parts['port']}/{parts['dbname']}"


def app_secret(create: bool = False) -> dict:
    """Read the app role's secret. With create=True a missing one gets a random password. Only the local emulator does this."""
    manager = client("secretsmanager")
    try:
        return json.loads(manager.get_secret_value(SecretId=APP_SECRET)["SecretString"])
    except ClientError as error:
        if not create or error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    parts = {"username": "hcp_app", "password": secrets.token_urlsafe(24), "host": "localhost", "port": 5433, "dbname": "hcp"}
    manager.create_secret(Name=APP_SECRET, SecretString=json.dumps(parts))
    return parts


@cache
def _app_url() -> str:
    return app_url(app_secret())


def __getattr__(name):  # APP_URL is read from Secrets Manager on first use
    if name == "APP_URL":
        return _app_url()
    raise AttributeError(name)


def owner_url(env=os.environ) -> str:
    """The migration role's URL. Use DATABASE_OWNER_URL, or build one from the cluster secret, or use the local owner."""
    url = env.get("DATABASE_OWNER_URL")
    if url:
        return url
    if all(name in env for name in ("DB_HOST", "DB_OWNER_USER", "DB_OWNER_PASSWORD")):
        return f"postgresql://{quote(env['DB_OWNER_USER'], safe='')}:{quote(env['DB_OWNER_PASSWORD'], safe='')}@{env['DB_HOST']}:5432/hcp"
    return "postgresql://hcp_owner:hcp_owner@localhost:5433/hcp"


OWNER_URL = owner_url()
MIGRATIONS = world.ROOT / "migrations"

DEFAULT_TENANT, current_tenant, as_tenant = world.DEFAULT_TENANT, world.current_tenant, world.as_tenant


@contextmanager
def session():
    """One transaction as the current tenant."""
    # Step 1: Open one transaction as the app user.
    with psycopg.connect(_app_url(), row_factory=dict_row) as conn, conn.transaction():
        # Step 2: Tell the database which tenant this is, so its row rules apply.
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (current_tenant(),))
        # Step 3: Hand the connection to the caller.
        yield conn


def is_up() -> bool:
    try:
        with psycopg.connect(_app_url(), connect_timeout=2):
            return True
    except (psycopg.Error, ClientError):
        return False


def migrate() -> list[str]:
    """Run each new file in migrations/ in name order, then sync the tenant list. Gives back what ran."""
    ran = []
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        done = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            ran.append(path.name)
        conn.execute(sql.SQL("ALTER ROLE hcp_app PASSWORD {}").format(sql.Literal(app_secret(create=True)["password"])))
        _app_url.cache_clear()
        for tenant in world.tenants():
            # The owner goes through RLS too, so it names the tenant it writes.
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant["id"],))
                conn.execute("INSERT INTO tenants (id, name) VALUES (%(id)s, %(name)s) "
                             "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name", tenant)
    return ran


def wipe() -> None:
    """Delete all documents of all tenants. The reset flag uses it."""
    for tenant in world.tenants():
        with as_tenant(tenant["id"]), session() as conn:
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM content_index")


if __name__ == "__main__":  # the ECS migration task: python -m hcpagents.db
    print("migrations applied:", ", ".join(migrate()) or "none new")
