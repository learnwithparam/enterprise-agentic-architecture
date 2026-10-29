"""Postgres, where every row belongs to a tenant and row-level security enforces it.

The app connects as hcp_app, which cannot bypass RLS. Each transaction names its tenant with
set_config('app.tenant_id', ..., true), so the setting ends with the transaction and can never leak
to the next one on the same connection. With no tenant set, every query returns no rows.
Migrations run as the owner, the only place that role is used.
"""

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from hcpagents import world

APP_URL = os.environ.get("DATABASE_URL", "postgresql://hcp_app:hcp_app@localhost:5433/hcp")
OWNER_URL = os.environ.get("DATABASE_OWNER_URL", "postgresql://hcp_owner:hcp_owner@localhost:5433/hcp")
MIGRATIONS = world.ROOT / "migrations"

DEFAULT_TENANT, current_tenant, as_tenant = world.DEFAULT_TENANT, world.current_tenant, world.as_tenant


@contextmanager
def session():
    """One transaction as the current tenant."""
    with psycopg.connect(APP_URL, row_factory=dict_row) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (current_tenant(),))
        yield conn


def up() -> bool:
    try:
        with psycopg.connect(APP_URL, connect_timeout=2):
            return True
    except psycopg.Error:
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
