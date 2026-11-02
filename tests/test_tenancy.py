"""Tenant isolation is a property of the database, so the tests walk the schema and then try to break it."""

import psycopg
import pytest

from hcpagents import db, infra, store

pytestmark = pytest.mark.floci

NOT_TENANT_DATA = {"schema_migrations"}  # owner-only bookkeeping; the app role has no grant on it


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def owner():
    return psycopg.connect(db.OWNER_URL, autocommit=True)


def test_every_table_forces_row_level_security_with_a_tenant_policy():
    with owner() as conn:
        tables = conn.execute(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'").fetchall()
        policies = {r[0]: r[1] for r in conn.execute("SELECT tablename, qual FROM pg_policies WHERE schemaname = 'public'")}
    assert {t[0] for t in tables} >= {"docs", "tenants"}
    for name, enabled, forced in tables:
        if name in NOT_TENANT_DATA:
            continue
        assert enabled and forced, f"{name} must ENABLE and FORCE row level security"
        assert "app.tenant_id" in policies.get(name, ""), f"{name} needs a policy on app.tenant_id"


def test_the_app_role_cannot_bypass_security_or_touch_bookkeeping():
    with owner() as conn:
        sup, bypass = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'hcp_app'").fetchone()
        grant = conn.execute("SELECT has_table_privilege('hcp_app', 'schema_migrations', 'SELECT')").fetchone()[0]
    assert not sup and not bypass and not grant


def test_a_second_tenant_cannot_see_or_change_the_first_tenants_rows():
    with owner() as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', 'acme', true)")
        conn.execute("INSERT INTO tenants (id, name) VALUES ('acme', 'Acme Pharma') ON CONFLICT DO NOTHING")
    try:
        with db.as_tenant("acme"):
            assert store.scan("mi-content") == [] and store.get("mi-content", "blk-vel-dosing-us") is None
            store.put("mi-content", {"id": "acme-only", "text": "x"})
            assert [d["id"] for d in store.scan("mi-content")] == ["acme-only"]
        assert store.get("mi-content", "acme-only") is None
        assert len(store.scan("mi-content")) > 1
    finally:
        with owner() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', 'acme', true)")
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM tenants WHERE id = 'acme'")


def test_writing_a_row_for_another_tenant_is_refused():
    with db.session() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO docs (tenant_id, kind, id, doc) VALUES ('acme', 'content', 'x', '{}')")


def test_with_no_tenant_set_nothing_is_visible():
    with psycopg.connect(db.APP_URL) as conn:  # the URL is read from Secrets Manager
        assert conn.execute("SELECT count(*) FROM docs").fetchone()[0] == 0


def test_every_table_a_migration_creates_declares_forced_rls_and_a_policy():
    """Reads the SQL itself, so a weakened migration fails before it is ever applied."""
    import re

    sql = "\n".join(f.read_text() for f in sorted(db.MIGRATIONS.glob("*.sql")))
    created = re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", sql)
    assert "docs" in created
    for table in created:
        if table in NOT_TENANT_DATA:
            continue
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql, table
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in sql, table
        assert re.search(rf"CREATE POLICY \w+ ON {table}\s+USING \(\w+ = current_setting\('app\.tenant_id', true\)\)", sql), table


def test_no_api_route_is_registered_after_the_page_catch_all():
    """A route added below `/{page:path}` is answered with HTML, so every /api route must come before it."""
    from hcpagents import api
    paths = [getattr(r, "path", "") for r in api.app.routes]
    if "/{page:path}" in paths:
        assert not [p for p in paths[paths.index("/{page:path}"):] if p.startswith("/api/")]


def test_autonomy_settings_isolated():
    """One tenant switching Germany off leaves every other tenant's Germany on, and a row for another tenant is refused."""
    from hcpagents import cases, world
    a, b = [t["id"] for t in world.tenants()][:2]
    with world.as_tenant(b):
        cases.save_autonomy("DE", cases.autonomy_setting("DE") | {"enabled": False})
        assert cases.autonomy_setting("DE")["enabled"] is False
    with world.as_tenant(a):
        assert cases.autonomy_setting("DE")["enabled"] is True
        with db.session() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO autonomy (tenant_id, country, enabled) VALUES (%s, 'FR', true)", (b,))


def test_autonomy_policy_is_in_the_migration():
    sql = (db.MIGRATIONS / "007_autonomy.sql").read_text()
    assert "FORCE ROW LEVEL SECURITY" in sql and "WITH CHECK" in sql


def test_queue_per_tenant(monkeypatch):
    import asyncio
    from hcpagents import durable, world
    ids = [t["id"] for t in world.tenants()]
    queues = [durable.queue_for(t) for t in ids]
    assert len(set(queues)) == len(ids) >= 2 and durable.PLATFORM_QUEUE not in queues
    started = []
    monkeypatch.setattr(durable, "worker", lambda client, queue=None, acts=None: _Recorder(started, queue))

    async def go():
        async with durable.workers(object()):
            pass
    asyncio.run(go())
    assert started == [durable.PLATFORM_QUEUE, *queues]


class _Recorder:
    def __init__(self, started, queue):
        self.started, self.queue = started, queue

    async def __aenter__(self):
        self.started.append(self.queue)

    async def __aexit__(self, *exc):
        return False


def test_worker_ignores_other_tenant_queue():
    """A case on one tenant's queue is never picked up by a worker that serves another tenant's queue."""
    import asyncio
    import uuid
    from hcpagents import durable, world
    from hcpagents.workflows import InquiryWorkflow
    a, b = [t["id"] for t in world.tenants()][:2]

    async def go():
        client = await durable.connect()
        wid = f"isolation-{uuid.uuid4().hex[:8]}"
        handle = await client.start_workflow(InquiryWorkflow.run, {"tenant": a, "inquiry_id": "inq-101", "inquiry": None},
                                             id=wid, task_queue=durable.queue_for(a))
        try:
            async with durable.worker(client, durable.queue_for(b)):
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(handle.result(), 3)
        finally:
            await handle.terminate()
    asyncio.run(go())
