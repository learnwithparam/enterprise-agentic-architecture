"""Keep a case alive with Temporal: a review nobody decides is escalated once, and a late decision still lands."""

import asyncio
import uuid

import pytest

from hcpagents import durable, infra, ledger, world
from hcpagents.workflows import InquiryWorkflow

pytestmark = pytest.mark.floci

BRANDT = world.person("u-brandt")


def types(case_id: str) -> list[str]:
    return [r["entry"]["type"] for r in ledger.entries(case_id)]


def run_with_deadline(sla_seconds: int):
    """Start inq-103 with a short reviewer deadline, wait for the overdue entry, then reject late."""
    queue = f"q-{uuid.uuid4().hex}"

    async def go():
        client = await durable.connect()
        async with durable.worker(client, queue):
            await client.execute_workflow(InquiryWorkflow.run, {"tenant": world.current_tenant(), "inquiry_id": "inq-103",
                                                                "review_sla_seconds": sla_seconds}, id=f"lab-{queue}", task_queue=queue)
            async with asyncio.timeout(20):
                while "review_overdue" not in types("inq-103"):
                    await asyncio.sleep(0.3)
            await asyncio.sleep(1.5)  # long enough for a second escalation, if the code were going to send one
            return await durable.decide("inq-103", BRANDT, "reject", note="late", client=client)

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def test_an_overdue_review_is_escalated_exactly_once():
    run_with_deadline(1)
    assert types("inq-103").count("review_overdue") == 1


def test_escalation_does_not_close_the_case_so_a_late_decision_still_lands():
    doc = run_with_deadline(1)
    assert doc["status"] == "rejected" and doc["escalated_at"]
