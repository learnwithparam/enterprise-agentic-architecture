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


def add_to(table: str, doc_id: str, field: str, amount: int) -> int:
    """Add to one number inside a document in a single statement, and return the new total.
    Two workers adding at once both count. A read then a put would lose one of them."""
    start = Jsonb({"id": doc_id, field: amount})
    with db.session() as conn:
        row = conn.execute(
            "INSERT INTO docs (tenant_id, kind, id, doc) VALUES (current_setting('app.tenant_id'), %s, %s, %s) "
            "ON CONFLICT (tenant_id, kind, id) DO UPDATE SET updated_at = now(), "
            "doc = jsonb_set(docs.doc, ARRAY[%s]::text[], to_jsonb(COALESCE((docs.doc ->> %s)::int, 0) + %s)) "
            "RETURNING (doc ->> %s)::int AS total",
            (_kind(table), doc_id, start, field, field, amount, field)).fetchone()
    return row["total"]


def scan(table: str) -> list[dict]:
    with db.session() as conn:
        return [row["doc"] for row in conn.execute("SELECT doc FROM docs WHERE kind = %s ORDER BY id", (_kind(table),))]


def content() -> dict[str, dict]:
    """The content store as it is now, keyed by block id."""
    return {block["id"]: block for block in scan("mi-content")}
