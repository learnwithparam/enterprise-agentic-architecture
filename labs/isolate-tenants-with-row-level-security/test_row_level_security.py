"""Isolate tenants with row level security: the database refuses the crossing, whatever the application code says."""

import psycopg
import pytest

from hcpagents import db, infra, store

pytestmark = pytest.mark.floci


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def test_with_no_tenant_set_the_app_role_sees_nothing():
    with psycopg.connect(db.APP_URL) as conn:
        assert conn.execute("SELECT count(*) FROM docs").fetchone()[0] == 0


def test_the_app_role_cannot_write_a_row_for_another_tenant():
    with db.session() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO docs (tenant_id, kind, id, doc) VALUES ('acme', 'content', 'x', '{}')")


def test_a_second_tenant_starts_with_an_empty_world():
    with psycopg.connect(db.OWNER_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO tenants (id, name) VALUES ('lab-co', 'Lab Co') ON CONFLICT DO NOTHING")
    try:
        with db.as_tenant("lab-co"):
            assert store.scan("mi-content") == []
        assert len(store.scan("mi-content")) > 1  # the first tenant's rows are still there, untouched
    finally:
        with psycopg.connect(db.OWNER_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM tenants WHERE id = 'lab-co'")


def test_the_docs_policy_in_the_migration_checks_the_tenant_on_read_and_write():
    """Reads the SQL itself, so a weakened migration fails before it is ever applied."""
    sql = (db.MIGRATIONS / "001_documents.sql").read_text()
    clause = "tenant_id = current_setting('app.tenant_id', true)"
    assert "ALTER TABLE docs FORCE ROW LEVEL SECURITY;" in sql
    assert f"USING ({clause})" in sql and f"WITH CHECK ({clause})" in sql
