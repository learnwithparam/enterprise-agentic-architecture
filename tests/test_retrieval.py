"""Retrieval ranks inside a hard gate; the gate, not the ranking, decides what a reply may be built from."""

import pytest

from hcpagents import db, embeddings, infra, retrieval, retrieval_eval

pytestmark = pytest.mark.floci


@pytest.fixture(scope="module", autouse=True)
def fresh():
    infra.provision(reset=True)


def ids(query, product, country, **kw):
    return [b["block_id"] for b in retrieval.search(query, product, country, **kw)]


def test_a_withdrawn_block_is_never_returned_even_when_the_question_quotes_it():
    found = ids("Store Veltrona below 30°C", "VEL", "DE", k=10)
    assert "VEL-DE-STOR" not in found and "VEL-DE-STOR3" in found


def test_an_expired_block_is_never_returned():
    assert "OMB-JP-INTER" not in ids("strong CYP3A4 inhibitors dose adjustment", "OMB", "JP", k=10)


def test_another_country_is_never_returned_whatever_the_question_says():
    found = retrieval.search("recommended dose 15 mg once daily", "VEL", "DE", k=20)
    assert found and all(b["block_id"].startswith(("VEL-DE", "ISI-VEL-DE")) for b in found)


def test_one_tenant_never_finds_another_tenants_blocks():
    with db.as_tenant("marlowe"):
        assert ids("recommended dose", "VEL", "US", k=10) == []


def test_vectors_from_a_different_model_are_never_compared(monkeypatch):
    real = embeddings.embedder()
    assert retrieval.search("dose", "VEL", "US", mode="vector")
    other = type("Other", (), {"model_id": "some-other-model", "dim": real.dim, "embed": staticmethod(real.embed)})()
    monkeypatch.setattr(embeddings, "embedder", lambda: other)
    assert retrieval.search("dose", "VEL", "US", mode="vector") == []


def test_hybrid_finds_every_answer_that_full_text_alone_misses():
    scores = retrieval_eval.run()
    assert scores["hybrid"]["recall_at_k"] == 1.0
    assert scores["fts"]["recall_at_k"] < scores["hybrid"]["recall_at_k"]
    assert all(s["outside_gate"] == 0 for s in scores.values())


def test_the_hashing_adapter_is_deterministic_and_unit_length():
    h = embeddings.HashingEmbedder()
    a, b = h.embed(["Veltrona dose"])[0], h.embed(["Veltrona dose"])[0]
    assert a == b and abs(sum(x * x for x in a) - 1.0) < 1e-9


def test_an_unknown_adapter_name_is_refused(monkeypatch):
    monkeypatch.setenv("MI_EMBEDDINGS", "nope")
    embeddings.embedder.cache_clear()
    try:
        with pytest.raises(ValueError):
            embeddings.embedder()
    finally:
        embeddings.embedder.cache_clear()
