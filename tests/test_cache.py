"""The retrieval cache never changes an answer: it is per tenant, it falls through when Valkey is down,
and withdrawing a block evicts every cached answer that quotes it (ADR 0018)."""

import asyncio
import uuid

import pytest
import valkey

from hcpagents import auth, cache, cases, durable, infra, ledger, retrieval, world

pytestmark = pytest.mark.floci

QUERY = ("Veltrona renal impairment dose", "VEL", "DE")
WEBER, BRANDT = world.person("u-weber"), world.person("u-brandt")


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


@pytest.fixture
def ranked(monkeypatch):
    """Counts how often the database was asked, so a hit is told apart from a miss."""
    calls = []
    real = retrieval._rank
    monkeypatch.setattr(retrieval, "_rank", lambda *a: calls.append(a) or real(*a))
    return calls


def test_the_same_question_is_answered_from_the_cache_the_second_time(ranked):
    first = retrieval.search(*QUERY)
    assert retrieval.search(*QUERY) == first and len(ranked) == 1


def test_another_tenant_never_reads_this_tenants_cached_answer(ranked):
    retrieval.search(*QUERY)
    with world.as_tenant("marlowe"):
        retrieval.search(*QUERY)
    assert len(ranked) == 2


def test_search_still_answers_when_valkey_is_down(monkeypatch):
    expected = retrieval.search(*QUERY, k=3)
    monkeypatch.setattr(cache, "_client", lambda: valkey.Valkey(port=1, socket_connect_timeout=0.2))
    assert retrieval.search(*QUERY, k=3) == expected


def test_withdrawing_a_block_evicts_every_cached_answer_that_quotes_it(ranked):
    block = retrieval.search(*QUERY)[0]["block_id"]
    out = cases.withdraw(block, WEBER, "Label update")
    assert out["cache_evicted"] == 1
    assert block not in [b["block_id"] for b in retrieval.search(*QUERY)] and len(ranked) == 2


def test_a_failed_eviction_is_recorded_and_the_withdrawal_still_happens(monkeypatch):
    block = retrieval.search(*QUERY)[0]["block_id"]
    monkeypatch.setattr(cache, "_client", lambda: valkey.Valkey(port=1, socket_connect_timeout=0.2))
    assert cases.withdraw(block, WEBER, "Label update")["cache_evicted"] is None
    assert "cache_evict_failed" in [r["entry"]["type"] for r in ledger.entries()]


def test_the_always_on_steward_invalidates_a_draft_when_content_is_withdrawn():
    """No caller processes the event: the steward workflow finds it on its own."""
    asyncio.run(cases.run("inq-103"))

    async def scenario():
        client, queue = await durable.connect(), f"q-{uuid.uuid4().hex}"
        async with durable.worker(client, queue):
            await durable.start_steward(client, queue, poll_seconds=0.2)
            cases.withdraw("VEL-DE-RENAL", WEBER, "Label update")
            async with asyncio.timeout(20):
                while "draft_invalidated" not in [r["entry"]["type"] for r in ledger.entries("inq-103")]:
                    await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert any("withdrawn" in p for p in cases.approve("inq-103", BRANDT, auth.reauthenticate(BRANDT, auth.DEMO_PASSWORD))["send_check"]["problems"])

