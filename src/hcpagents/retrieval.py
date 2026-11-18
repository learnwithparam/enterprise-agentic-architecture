"""Hybrid search over approved content (ADR 0012).

Two layers, in this order:
1. The facet gate is a hard filter in SQL. It checks tenant, product, country, approval and the approval dates.
   Nothing outside it can come back.
2. Inside the gate, text rank and vector rank are joined with rank fusion.

A search on meaning alone could return a US dose for a German question. So the gate comes first.
"""

import re

from hcpagents import cache, db, embeddings, store, world

RRF_K = 60  # the fusion constant; a bigger number makes top ranks count less

GATE = """
    d.kind = 'content'
    AND d.doc ->> 'product' = %(product)s AND d.doc ->> 'country' = %(country)s
    AND d.doc ->> 'status' = 'approved'
    AND (d.doc ->> 'approved_on')::date <= %(today)s AND %(today)s <= (d.doc ->> 'expires_on')::date
"""
TOPIC_CLAUSE = "AND (%(topic)s::text IS NULL OR d.doc ->> 'topic' = %(topic)s)"


def index() -> int:
    """Embed each content block of the current tenant under the active model. Gives back how many."""
    blocks = list(store.content().values())
    embedder = embeddings.embedder()
    vectors = embedder.embed([block["text"] for block in blocks])
    with db.session() as conn:
        for block, vector in zip(blocks, vectors, strict=True):
            conn.execute(
                "INSERT INTO content_index (tenant_id, block_id, model_id, dim, embedding) "
                "VALUES (current_setting('app.tenant_id'), %s, %s, %s, %s::vector) "
                "ON CONFLICT (tenant_id, block_id, model_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (block["id"], embedder.model_id, embedder.dim, embeddings.literal(vector)))
    cache.flush_tenant(world.current_tenant())
    return len(blocks)


def search(query: str, product: str, country: str, topic: str | None = None, limit: int = 5,
           mode: str = "hybrid", **aliases) -> list[dict]:
    """The best current blocks for a question. A cache answers if the same question came up lately (ADR 0018).

    The topic narrows the search inside the gate when the caller knows it. The old name k still works for limit.
    The mode "fts" or "vector" ranks with one signal only. The eval compares them with "hybrid".
    """
    if "k" in aliases:
        limit = aliases["k"]
    tenant = world.current_tenant()
    cache_key = cache.key(tenant, query=query, product=product, country=country, topic=topic, k=limit, mode=mode,
                          today=world.TODAY, model=embeddings.embedder().model_id)
    hit = cache.get(cache_key)
    if hit is not None:
        return hit
    results = _rank(query, product, country, topic, limit, mode)
    cache.put(tenant, cache_key, results)
    return results


def _full_text(conn, params: dict) -> list[dict]:
    return conn.execute(f"""
            SELECT d.id FROM docs d WHERE {GATE} {TOPIC_CLAUSE}
              AND to_tsvector('simple', d.doc ->> 'text') @@ to_tsquery('simple', %(words)s)
            ORDER BY ts_rank(to_tsvector('simple', d.doc ->> 'text'), to_tsquery('simple', %(words)s)) DESC, d.id
            LIMIT %(pool)s""", params).fetchall()


def _by_vector(conn, params: dict) -> list[dict]:
    return conn.execute(f"""
            SELECT d.id FROM docs d JOIN content_index c
              ON c.block_id = d.id AND c.tenant_id = d.tenant_id AND c.model_id = %(model)s
            WHERE {GATE} {TOPIC_CLAUSE}
            ORDER BY c.embedding <=> %(vec)s::vector, d.id
            LIMIT %(pool)s""", params).fetchall()


def _best_first(score: dict[str, float]) -> list[str]:
    def order(block_id: str) -> tuple:
        return -score[block_id], block_id

    return sorted(score, key=order)


def _rank(query: str, product: str, country: str, topic: str | None, limit: int, mode: str) -> list[dict]:
    # Step 1: Turn the question into words and a vector.
    embedder = embeddings.embedder()
    params = {"product": product, "country": country, "today": world.TODAY, "topic": topic,
              "words": " | ".join(re.findall(r"\w+", query.lower())) or "''",
              "vec": embeddings.literal(embedder.embed([query])[0]), "model": embedder.model_id,
              "pool": max(limit * 4, 20)}
    with db.session() as conn:
        full_text, by_vector = [], []
        # Step 2: Rank inside the facet gate by text and by vector.
        if mode != "vector":
            full_text = _full_text(conn, params)
        if mode != "fts":
            by_vector = _by_vector(conn, params)
        # Step 3: Join the two ranks with rank fusion.
        score: dict[str, float] = {}
        for ranked in (full_text, by_vector):
            for rank, row in enumerate(ranked, start=1):
                score[row["id"]] = score.get(row["id"], 0.0) + 1.0 / (RRF_K + rank)
        # Step 4: Keep the best blocks and read them.
        top = _best_first(score)[:limit]
        by_id = {row["id"]: row["doc"] for row in conn.execute(
            "SELECT id, doc FROM docs WHERE kind = 'content' AND id = ANY(%s)", (top,))}
    return [{"block_id": by_id[block_id]["id"], "version": by_id[block_id]["version"],
             "topic": by_id[block_id]["topic"], "text": by_id[block_id]["text"],
             "score": round(score[block_id], 5)} for block_id in top]
