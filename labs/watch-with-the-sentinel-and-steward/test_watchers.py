"""Watch with the sentinel and the steward: nobody asks them, and a read twice is one signal."""

import asyncio
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, auth, cases, durable, events, infra, ingest, ledger, sentinel, world

pytestmark = pytest.mark.floci

WEBER, BRANDT = world.person("u-weber"), world.person("u-brandt")


def send(c, channel, source_id, text, tenant="quillon") -> str:
    body = json.dumps({"external_id": uuid.uuid4().hex, "source_id": source_id, "kind": "visit_note", "text": text,
                       "occurred_at": "2026-10-28T09:30:00Z"}).encode()
    ts = int(time.time())
    sig = ingest.sign(ingest.secret_for(tenant, channel), ts, body)
    r = c.post(f"/hooks/{tenant}/{channel}", content=body, headers={"x-mi-timestamp": str(ts), "x-mi-signature": sig})
    assert r.status_code == 202
    return r.json()["id"]


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def test_a_rash_in_a_rep_note_reaches_pharmacovigilance_with_nobody_asking():
    note = send(TestClient(api.app), "crm", "CRM-DE-00977", "Patient on Veltrona developed a rash after two weeks.")
    assert sentinel.perceive() == 1
    got: list[dict] = []
    with world.as_tenant("quillon"):
        events.consume("mi-pv-intake", got.append)
    assert [s["interaction"] for s in got] == [note]


def test_the_same_event_read_twice_raises_one_signal():
    send(TestClient(api.app), "crm", "CRM-DE-00977", "Swelling reported by a patient.")
    assert sentinel.perceive() == 1 and sentinel.perceive() == 0


def test_the_steward_invalidates_a_draft_when_content_is_withdrawn():
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
    problems = cases.approve("inq-103", BRANDT, auth.reauthenticate(BRANDT, auth.DEMO_PASSWORD))["send_check"]["problems"]
    assert any("withdrawn" in p for p in problems)
