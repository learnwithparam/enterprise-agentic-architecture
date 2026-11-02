"""Retrieve behind a facet gate: ranking decides the order, the gate decides what may be returned at all."""

import pytest

from hcpagents import db, infra, retrieval

pytestmark = pytest.mark.floci


@pytest.fixture(scope="module", autouse=True)
def fresh():
    infra.provision(reset=True)


def ids(query, product, country, **kw):
    return [b["block_id"] for b in retrieval.search(query, product, country, **kw)]


def test_a_withdrawn_block_is_never_returned_even_when_the_question_quotes_it():
    found = ids("Store Veltrona below 30°C", "VEL", "DE", k=10)
    assert "VEL-DE-STOR" not in found and "VEL-DE-STOR3" in found


def test_another_country_is_never_returned_whatever_the_question_says():
    found = retrieval.search("recommended dose 15 mg once daily", "VEL", "DE", k=20)
    assert found and all(b["block_id"].startswith(("VEL-DE", "ISI-VEL-DE")) for b in found)


def test_another_tenant_finds_nothing():
    with db.as_tenant("marlowe"):
        assert ids("recommended dose", "VEL", "US", k=10) == []
