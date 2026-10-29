"""Hybrid retrieval over approved content (ADR 0012).

Two layers, in this order:
1. The facet gate is a hard filter in SQL: tenant (row-level security), product, country, approved,
   and today inside the approval window. Nothing outside it can be returned, whatever the ranking says.
2. Inside the gate, full-text rank and vector rank are fused with reciprocal rank fusion.
Similarity alone would happily return an American dose for a German question, which is why the gate comes first.
"""

import re

from hcpagents import cache, db, embeddings, store, world

RRF_K = 60  # the constant from the original reciprocal rank fusion paper; larger flattens the difference between ranks

GATE = """
    d.kind = 'content'
    AND d.doc ->> 'product' = %(product)s AND d.doc ->> 'country' = %(country)s
    AND d.doc ->> 'status' = 'approved'
    AND (d.doc ->> 'approved_on')::date <= %(today)s AND %(today)s <= (d.doc ->> 'expires_on')::date
"""


def index() -> int:
    """Embed every content block of the current tenant under the active model. Returns how many."""
    blocks = list(store.content().values())
    emb = embeddings.embedder()
    vectors = emb.embed([b["text"] for b in blocks])
    with db.session() as conn:
        for b, v in zip(blocks, vectors, strict=True):
            conn.execute(
                "INSERT INTO content_index (tenant_id, block_id, model_id, dim, embedding) "
                "VALUES (current_setting('app.tenant_id'), %s, %s, %s, %s::vector) "
                "ON CONFLICT (tenant_id, block_id, model_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (b["id"], emb.model_id, emb.dim, embeddings.literal(v)))
    cache.flush_tenant(world.current_tenant())
    return len(blocks)


def search(query: str, product: str, country: str, topic: str | None = None, k: int = 5, mode: str = "hybrid") -> list[dict]:
    """The best k current blocks for a question, from the cache when this exact question was asked recently (ADR 0018).

    `topic` narrows inside the gate when the caller already knows it. mode "fts" or "vector" ranks with
    one signal only; the retrieval eval compares them with "hybrid".
    """
    tenant = world.current_tenant()
    k_ = cache.key(tenant, query=query, product=product, country=country, topic=topic, k=k, mode=mode,
                   today=world.TODAY, model=embeddings.embedder().model_id)
    if (hit := cache.get(k_)) is not None:
        return hit
    results = _rank(query, product, country, topic, k, mode)
    cache.put(tenant, k_, results)
    return results


def _rank(query: str, product: str, country: str, topic: str | None, k: int, mode: str) -> list[dict]:
    emb = embeddings.embedder()
    params = {"product": product, "country": country, "today": world.TODAY, "topic": topic, "words": " | ".join(re.findall(r"\w+", query.lower())) or "''",
              "vec": embeddings.literal(emb.embed([query])[0]), "model": emb.model_id, "pool": max(k * 4, 20)}
    topic_clause = "AND (%(topic)s::text IS NULL OR d.doc ->> 'topic' = %(topic)s)"
    with db.session() as conn:
        fts = conn.execute(f"""
            SELECT d.id FROM docs d WHERE {GATE} {topic_clause}
              AND to_tsvector('simple', d.doc ->> 'text') @@ to_tsquery('simple', %(words)s)
            ORDER BY ts_rank(to_tsvector('simple', d.doc ->> 'text'), to_tsquery('simple', %(words)s)) DESC, d.id
            LIMIT %(pool)s""", params).fetchall() if mode != "vector" else []
        vec = conn.execute(f"""
            SELECT d.id FROM docs d JOIN content_index c
              ON c.block_id = d.id AND c.tenant_id = d.tenant_id AND c.model_id = %(model)s
            WHERE {GATE} {topic_clause}
            ORDER BY c.embedding <=> %(vec)s::vector, d.id
            LIMIT %(pool)s""", params).fetchall() if mode != "fts" else []
        score: dict[str, float] = {}
        for ranked in (fts, vec):
            for rank, row in enumerate(ranked, start=1):
                score[row["id"]] = score.get(row["id"], 0.0) + 1.0 / (RRF_K + rank)
        top = sorted(score, key=lambda i: (-score[i], i))[:k]
        by_id = {r["id"]: r["doc"] for r in conn.execute(
            "SELECT id, doc FROM docs WHERE kind = 'content' AND id = ANY(%s)", (top,))}
    return [{"block_id": by_id[i]["id"], "version": by_id[i]["version"], "topic": by_id[i]["topic"],
             "text": by_id[i]["text"], "score": round(score[i], 5)} for i in top]
