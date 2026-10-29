"""Channels reach the platform through a signed webhook or a nightly batch, and either way an event lands once (ADR 0021)."""

import asyncio
import contextlib
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, db, durable, infra, ingest, world
from hcpagents.aws import client

pytestmark = pytest.mark.floci


@pytest.fixture(autouse=True)
def fresh():
    global WHO
    WHO = "src-" + uuid.uuid4().hex
    infra.provision(reset=True)


WHO = ""  # a new person id per test: the interaction log is never wiped, so each test reads back only its own rows


def record(**over) -> dict:
    return {"external_id": uuid.uuid4().hex, "source_id": WHO, "kind": "visit_note",
            "text": "Doctor asked about renal dosing.", "occurred_at": "2026-10-28T09:30:00Z"} | over


def post(c, tenant, channel, rec, secret_tenant=None, ts=None, tamper=False):
    body = json.dumps(rec).encode()
    ts = int(time.time()) if ts is None else ts
    sig = ingest.sign(ingest.secret_for(secret_tenant or tenant, channel), ts, body)
    if tamper:
        body += b" "
    return c.post(f"/hooks/{tenant}/{channel}", content=body, headers={"x-mi-timestamp": str(ts), "x-mi-signature": sig})


def rows(tenant) -> list[dict]:
    with world.as_tenant(tenant), db.session() as conn:
        return conn.execute("SELECT * FROM interactions WHERE source_id = %s", (WHO,)).fetchall()


def test_a_signed_webhook_is_stored_and_the_same_event_again_changes_nothing():
    c, rec = TestClient(api.app), record()
    first, again = post(c, "quillon", "crm", rec), post(c, "quillon", "crm", rec)
    assert first.status_code == again.status_code == 202
    assert first.json()["duplicate"] is False and again.json() == {"id": first.json()["id"], "duplicate": True}
    assert [r["id"] for r in rows("quillon")] == [first.json()["id"]]


def test_a_request_that_is_not_signed_by_the_channel_is_refused_and_stores_nothing():
    c, rec = TestClient(api.app), record()
    assert post(c, "quillon", "crm", rec, tamper=True).status_code == 401
    assert post(c, "quillon", "crm", rec, secret_tenant="marlowe").status_code == 401
    assert post(c, "quillon", "crm", rec, ts=int(time.time()) - 3600).status_code == 401
    assert c.post("/hooks/quillon/crm", json=rec).status_code == 401
    assert post(c, "quillon", "fax", rec).status_code == 404
    assert post(c, "nowhere", "crm", rec).status_code == 404
    assert rows("quillon") == []


def test_a_signed_body_that_is_not_a_record_is_refused():
    assert post(TestClient(api.app), "quillon", "portal", {"text": "no ids"}).status_code == 422


def test_one_tenants_interactions_are_invisible_to_another():
    post(TestClient(api.app), "quillon", "portal", record())
    assert len(rows("quillon")) == 1 and rows("marlowe") == []


def test_a_batch_file_is_ingested_once_moved_aside_and_bad_lines_do_not_stop_it():
    s3, dup = client("s3"), record()
    lines = [json.dumps(record()), json.dumps(dup), json.dumps(dup), "not json", json.dumps({"text": "no ids"})]
    s3.put_object(Bucket=ingest.BUCKET, Key="quillon/marketing/incoming/night-1.jsonl", Body="\n".join(lines).encode())
    assert ingest.import_batch("quillon") == {"new": 2, "duplicate": 1, "rejected": 2, "files": 1}
    assert ingest.import_batch("quillon")["files"] == 0
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=ingest.BUCKET, Prefix="quillon/marketing/").get("Contents", [])]
    assert keys == ["quillon/marketing/done/night-1.jsonl"]


def test_the_nightly_schedule_exists_once_per_tenant_and_runs_the_import():
    client("s3").put_object(Bucket=ingest.BUCKET, Key="marlowe/contact_centre/incoming/a.jsonl", Body=json.dumps(record()).encode())

    async def scenario():
        tc, queue = await durable.connect(), f"q-{uuid.uuid4().hex}"
        for t in world.tenants():
            with contextlib.suppress(Exception):  # nothing to delete the first time
                await tc.get_schedule_handle(durable.schedule_id(t["id"])).delete()
        await durable.ensure_schedules(tc, queue)
        await durable.ensure_schedules(tc, queue)
        ids = {s.id async for s in await tc.list_schedules()}
        assert {durable.schedule_id(t["id"]) for t in world.tenants()} <= ids
        async with durable.worker(tc, queue):
            await tc.get_schedule_handle(durable.schedule_id("marlowe")).trigger()
            async with asyncio.timeout(20):
                while not rows("marlowe"):
                    await asyncio.sleep(0.3)

    asyncio.run(scenario())
    assert len(rows("marlowe")) == 1
