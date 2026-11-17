"""JSON documents in Postgres, one row per document, kept apart for each tenant.
Content, cases, doctors and touches all use this. The table name keeps its old mi- prefix."""

from psycopg.types.json import Jsonb

from hcpagents import db


def _kind(table: str) -> str:
    return table.removeprefix("mi-")


def get(table: str, doc_id: str) -> dict | None:
    with db.session() as conn:
        row = conn.execute("SELECT doc FROM docs WHERE kind = %s AND id = %s", (_kind(table), doc_id)).fetchone()
    if row:
        return row["doc"]
    return None


def put(table: str, doc: dict) -> None:
    with db.session() as conn:
        conn.execute(
            "INSERT INTO docs (tenant_id, kind, id, doc) VALUES (current_setting('app.tenant_id'), %s, %s, %s) "
            "ON CONFLICT (tenant_id, kind, id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()",
            (_kind(table), doc["id"], Jsonb(doc)))


def scan(table: str) -> list[dict]:
    with db.session() as conn:
        return [row["doc"] for row in conn.execute("SELECT doc FROM docs WHERE kind = %s ORDER BY id", (_kind(table),))]


def content() -> dict[str, dict]:
    """The content store as it is now, keyed by block id."""
    return {block["id"]: block for block in scan("mi-content")}
