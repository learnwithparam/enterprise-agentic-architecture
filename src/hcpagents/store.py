"""JSON documents in Postgres, one row per document, scoped to the current tenant by row-level security.
Content, cases, HCPs and touches all use this. `table` keeps its old mi-* name so callers did not change."""

from psycopg.types.json import Jsonb

from hcpagents import db


def _kind(table: str) -> str:
    return table.removeprefix("mi-")


def get(table: str, doc_id: str) -> dict | None:
    with db.session() as conn:
        row = conn.execute("SELECT doc FROM docs WHERE kind = %s AND id = %s", (_kind(table), doc_id)).fetchone()
    return row["doc"] if row else None


def put(table: str, doc: dict) -> None:
    with db.session() as conn:
        conn.execute(
            "INSERT INTO docs (tenant_id, kind, id, doc) VALUES (current_setting('app.tenant_id'), %s, %s, %s) "
            "ON CONFLICT (tenant_id, kind, id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()",
            (_kind(table), doc["id"], Jsonb(doc)))


def scan(table: str) -> list[dict]:
    with db.session() as conn:
        return [r["doc"] for r in conn.execute("SELECT doc FROM docs WHERE kind = %s ORDER BY id", (_kind(table),))]


def content() -> dict[str, dict]:
    """The content store as it is now, keyed by block id."""
    return {b["id"]: b for b in scan("mi-content")}
