"""Start cases on Temporal and serve the worker that runs them.

uv run python -m hcpagents.worker      # the worker as its own process
"""

import asyncio
import os

from temporalio.client import (Client, Schedule, ScheduleActionStartWorkflow, ScheduleAlreadyRunningError, ScheduleOverlapPolicy,
                              SchedulePolicy, ScheduleSpec)
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from hcpagents import activities, cases, world
from hcpagents.workflows import BatchImportWorkflow, ContentStewardWorkflow, InquiryWorkflow, ReviewWorkflow, review_id

ADDRESS = os.environ.get("MI_TEMPORAL", "localhost:7233")
QUEUE = "hcp-cases"
STEWARD_ID = "content-steward"
ACTIVITIES = [activities.open_case, activities.run_step, activities.close_case, activities.decide_case, activities.escalate_case,
              activities.steward_tick, activities.import_batch]


async def connect() -> Client:
    return await Client.connect(ADDRESS)


def workflow_id(tenant: str, inquiry_id: str) -> str:
    return f"inquiry-{tenant}-{inquiry_id}"


def worker(client: Client, queue: str = QUEUE, acts: list | None = None) -> Worker:
    return Worker(client, task_queue=queue, workflows=[InquiryWorkflow, ReviewWorkflow, ContentStewardWorkflow, BatchImportWorkflow], activities=acts or ACTIVITIES)


async def run_inquiry(inquiry_id: str, inquiry: dict | None = None, client: Client | None = None, queue: str = QUEUE) -> dict:
    """Run one inquiry as a workflow. Asking for one that is already running joins it instead of starting a second."""
    tenant = world.current_tenant()
    client = client or await connect()
    return await client.execute_workflow(
        InquiryWorkflow.run, {"tenant": tenant, "inquiry_id": inquiry_id, "inquiry": inquiry},
        id=workflow_id(tenant, inquiry_id), task_queue=queue, id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)


async def decide(case_id: str, user: dict, action: str, note: str = "", signature: dict | None = None,
                 client: Client | None = None) -> dict:
    """Give the reviewer's decision to the workflow waiting on this case. No waiting workflow means no decision."""
    tenant = world.current_tenant()
    client = client or await connect()
    args = {"tenant": tenant, "case_id": case_id, "user": user, "action": action, "note": note, "signature": signature}
    try:
        res = await client.get_workflow_handle(review_id(tenant, case_id)).execute_update(ReviewWorkflow.decide, args)
    except RPCError as e:
        if e.status != RPCStatusCode.NOT_FOUND:
            raise
        raise cases.Denied(f"Case {case_id} is not waiting for a reviewer") from e
    if "denied" in res:
        raise cases.Denied(res["denied"])
    return res["doc"]


async def start_steward(client: Client, queue: str = QUEUE, poll_seconds: float | None = None) -> None:
    """Make sure the content steward is running. Starting it twice leaves the one that is already on."""
    args = {} if poll_seconds is None else {"poll_seconds": poll_seconds}
    await client.start_workflow(ContentStewardWorkflow.run, args, id=STEWARD_ID, task_queue=queue,
                                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)


def schedule_id(tenant: str) -> str:
    return f"batch-import-{tenant}"


async def ensure_schedules(client: Client, queue: str = QUEUE, cron: str = "0 2 * * *") -> None:
    """One nightly batch import per tenant, 02:00 UTC. Creating one that exists leaves it as it is."""
    for t in world.tenants():
        action = ScheduleActionStartWorkflow(BatchImportWorkflow.run, {"tenant": t["id"]}, id=f"batch-import-run-{t['id']}", task_queue=queue)
        schedule = Schedule(action=action, spec=ScheduleSpec(cron_expressions=[cron]), policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP))
        try:
            await client.create_schedule(schedule_id(t["id"]), schedule)
        except ScheduleAlreadyRunningError:
            continue


async def serve() -> None:
    client = await connect()
    async with worker(client):
        await start_steward(client)
        await ensure_schedules(client)
        await asyncio.Event().wait()
