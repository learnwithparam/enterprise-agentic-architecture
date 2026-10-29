"""A case is a Temporal workflow: same answers as the in-process run, resumable on another worker, never started twice."""

import asyncio
import uuid

import pytest

from hcpagents import activities, auth, cases, durable, infra, ledger, store, world
from hcpagents.workflows import InquiryWorkflow

pytestmark = pytest.mark.floci

SAMPLE = ["inq-101", "inq-103", "inq-105"]


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def types(case_id: str) -> list[str]:
    return [r["entry"]["type"] for r in ledger.entries(case_id)]


async def in_workflow(inquiry_id: str, queue: str) -> dict:
    client = await durable.connect()
    async with durable.worker(client, queue):
        return await durable.run_inquiry(inquiry_id, client=client, queue=queue)


@pytest.mark.parametrize("inquiry_id", SAMPLE)
def test_a_workflow_reaches_the_same_route_facts_and_ledger_as_the_in_process_run(inquiry_id):
    local = asyncio.run(cases.run(inquiry_id))
    local_types = types(inquiry_id)
    infra.provision(reset=True)
    remote = asyncio.run(in_workflow(inquiry_id, f"q-{uuid.uuid4().hex}"))
    assert (remote["route"], remote["facts"], remote["status"]) == (local["route"], local["facts"], local["status"])
    assert types(inquiry_id) == local_types


def test_another_worker_resumes_a_case_from_temporal_history_without_repeating_a_step():
    queue, inquiry_id = f"q-{uuid.uuid4().hex}", "inq-105"

    async def go():
        client = await durable.connect()
        handle = await client.start_workflow(InquiryWorkflow.run, {"tenant": world.current_tenant(), "inquiry_id": inquiry_id},
                                             id=f"resume-{queue}", task_queue=queue)
        async with durable.worker(client, queue, [activities.open_case]):  # this worker dies after opening the case
            while "case_received" not in types(inquiry_id):
                await asyncio.sleep(0.2)
        async with durable.worker(client, queue):
            return await handle.result()

    d = asyncio.run(go())
    assert d["route"] and types(inquiry_id).count("case_received") == 1 and types(inquiry_id).count("routed") == 1


def test_asking_twice_for_the_same_inquiry_joins_one_workflow():
    queue = f"q-{uuid.uuid4().hex}"

    async def go():
        client = await durable.connect()
        async with durable.worker(client, queue):
            return await asyncio.gather(*(durable.run_inquiry("inq-101", client=client, queue=queue) for _ in range(2)))

    a, b = asyncio.run(go())
    assert a["route"] == b["route"] and types("inq-101").count("case_received") == 1


def test_an_activity_refuses_a_step_the_kernel_does_not_know():
    from temporalio.exceptions import ApplicationError
    with pytest.raises(ApplicationError):
        asyncio.run(activities.run_step({"tenant": "quillon", "doc": {}, "node": "__init__"}))


BRANDT, HALE = world.person("u-brandt"), world.person("u-hale")


def signed(user):
    return auth.reauthenticate(user, auth.DEMO_PASSWORD)


async def review_session(queue, body, **kw):
    """Run inq-103 to its review wait on a worker, then call `body(client)` while the worker is up."""
    client = await durable.connect()
    async with durable.worker(client, queue):
        d = await durable.run_inquiry("inq-103", client=client, queue=queue)
        return d, await body(client)


def test_a_case_in_review_waits_for_a_reviewer_and_approval_sends_it():
    async def body(client):
        with pytest.raises(cases.Denied):  # wrong country: Cedar refuses inside the workflow, the wait goes on
            await durable.decide("inq-103", HALE, "approve", signature=signed(HALE), client=client)
        return await durable.decide("inq-103", BRANDT, "approve", signature=signed(BRANDT), client=client)

    d, approved = asyncio.run(review_session(f"q-{uuid.uuid4().hex}", body))
    assert d["status"] == "awaiting_review" and approved["status"] == "sent"
    assert types("inq-103").count("e_signature") == 1


def test_approval_without_a_fresh_signature_is_refused_and_the_case_stays_open():
    old = signed(BRANDT) | {"at": "2020-01-01T00:00:00+00:00"}

    async def body(client):
        for sig in (None, old, signed(HALE)):
            with pytest.raises(cases.Denied, match="sign in again"):
                await durable.decide("inq-103", BRANDT, "approve", signature=sig, client=client)

    asyncio.run(review_session(f"q-{uuid.uuid4().hex}", body))
    assert store.get("mi-cases", "inq-103")["status"] == "awaiting_review" and "e_signature" not in types("inq-103")


def test_a_review_nobody_decides_is_escalated_once_and_stays_open():
    queue = f"q-{uuid.uuid4().hex}"

    async def go():
        client = await durable.connect()
        async with durable.worker(client, queue):
            await client.execute_workflow(InquiryWorkflow.run, {"tenant": world.current_tenant(), "inquiry_id": "inq-103",
                                                                "review_sla_seconds": 1}, id=f"sla-{queue}", task_queue=queue)
            async with asyncio.timeout(15):  # escalation is due after 1 second
                while "review_overdue" not in types("inq-103"):
                    await asyncio.sleep(0.3)
            await asyncio.sleep(1.5)
            return await durable.decide("inq-103", BRANDT, "reject", note="late", client=client)

    d = asyncio.run(go())
    assert types("inq-103").count("review_overdue") == 1 and d["status"] == "rejected" and d["escalated_at"]


def test_deciding_a_case_nobody_is_waiting_on_is_refused():
    asyncio.run(cases.run("inq-103"))  # in process: no review workflow exists
    with pytest.raises(cases.Denied, match="not waiting"):
        asyncio.run(durable.decide("inq-103", BRANDT, "reject", note="x"))
