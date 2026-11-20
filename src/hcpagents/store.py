"""JSON documents in Postgres, one row per document, kept apart for each tenant.
Content, cases, doctors and touches all use this. The table name keeps its old mi- prefix."""

from psycopg import sql
from psycopg.types.json import Jsonb

from hcpagents import db

# Which zone holds each kind. Anything not listed is shared and lives in public.docs.
ZONES = {
    "medical": ("cases", "reviewer-queue", "medical-review", "review-overdue", "inquiry-graph", "draft-sources"),
    "safety": ("pv-intake", "pv-manual-screening", "detector-health", "freezes"),
    "commercial": ("hcp", "touches", "proposals"),
}
ZONE_OF = {}
for _zone, _kinds in ZONES.items():
    for _kind_name in _kinds:
        ZONE_OF[_kind_name] = _zone


def zone_of(table: str) -> str:
    """The zone that owns this kind of document."""
    return ZONE_OF.get(_kind(table), "shared")


def _docs(kind: str) -> sql.Identifier:
    zone = ZONE_OF.get(kind)
    if zone is None:
        return sql.Identifier("public", "docs")
    return sql.Identifier(zone, "docs")


def _kind(table: str) -> str:
    return table.removeprefix("mi-")


def get(table: str, doc_id: str) -> dict | None:
    with db.session() as conn:
        row = conn.execute(sql.SQL("SELECT doc FROM {} WHERE kind = %s AND id = %s").format(_docs(_kind(table))),
                           (_kind(table), doc_id)).fetchone()
    if row:
        return row["doc"]
    return None


def put(table: str, doc: dict) -> None:
    with db.session() as conn:
        conn.execute(sql.SQL(
            "INSERT INTO {0} (tenant_id, kind, id, doc) VALUES (current_setting('app.tenant_id'), %s, %s, %s) "
            "ON CONFLICT (tenant_id, kind, id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()").format(_docs(_kind(table))),
            (_kind(table), doc["id"], Jsonb(doc)))


def add_to(table: str, doc_id: str, field: str, amount: int) -> int:
    """Add to one number inside a document in a single statement, and return the new total.
    Two workers adding at once both count. A read then a put would lose one of them."""
    start = Jsonb({"id": doc_id, field: amount})
    with db.session() as conn:
        row = conn.execute(sql.SQL(
            "INSERT INTO {0} AS t (tenant_id, kind, id, doc) VALUES (current_setting('app.tenant_id'), %s, %s, %s) "
            "ON CONFLICT (tenant_id, kind, id) DO UPDATE SET updated_at = now(), "
            "doc = jsonb_set(t.doc, ARRAY[%s]::text[], to_jsonb(COALESCE((t.doc ->> %s)::int, 0) + %s)) "
            "RETURNING (t.doc ->> %s)::int AS total").format(_docs(_kind(table))),
            (_kind(table), doc_id, start, field, field, amount, field)).fetchone()
    return row["total"]


def scan(table: str) -> list[dict]:
    with db.session() as conn:
        rows = conn.execute(sql.SQL("SELECT doc FROM {} WHERE kind = %s ORDER BY id").format(_docs(_kind(table))), (_kind(table),))
        return [row["doc"] for row in rows]


def scan_prefix(table: str, prefix: str) -> list[dict]:
    """Every document whose id starts with the prefix. The id index serves it, so no other row is read."""
    with db.session() as conn:
        rows = conn.execute(sql.SQL("SELECT doc FROM {} WHERE kind = %s AND starts_with(id, %s) ORDER BY id").format(
            _docs(_kind(table))), (_kind(table), prefix))
        return [row["doc"] for row in rows]


def content() -> dict[str, dict]:
    """The content store as it is now, keyed by block id."""
    return {block["id"]: block for block in scan("mi-content")}
