"""Start cases on Temporal and serve the worker that runs them.

uv run python -m hcpagents.worker      # the worker as its own process
"""

import asyncio
import contextlib
import os

from temporalio.client import (Client, Schedule, ScheduleActionStartWorkflow, ScheduleAlreadyRunningError, ScheduleOverlapPolicy,
                              SchedulePolicy, ScheduleSpec)
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from hcpagents import activities, cases, world
from hcpagents.workflows import BatchImportWorkflow, ContentStewardWorkflow, InquiryWorkflow, ReviewWorkflow, review_id

ADDRESS = os.environ.get("MI_TEMPORAL", "localhost:7233")
PLATFORM_QUEUE = "hcp-platform"  # Work that belongs to no tenant, such as the content steward.


def queue_for(tenant: str) -> str:
    """Each tenant has its own task queue, so a worker serves only its tenants."""
    return f"cases-{tenant}"


STEWARD_ID = "content-steward"
ACTIVITIES = [activities.open_case, activities.run_step, activities.close_case, activities.decide_case, activities.escalate_case,
              activities.steward_tick, activities.import_batch]


async def connect() -> Client:
    return await Client.connect(ADDRESS)


def workflow_id(tenant: str, inquiry_id: str) -> str:
    return f"inquiry-{tenant}-{inquiry_id}"


def worker(client: Client, queue: str | None = None, acts: list | None = None) -> Worker:
    """A worker for one queue (the current tenant's when none is named)."""
    return Worker(client, task_queue=queue or queue_for(world.current_tenant()), workflows=[InquiryWorkflow, ReviewWorkflow, ContentStewardWorkflow, BatchImportWorkflow], activities=acts or ACTIVITIES)


async def run_inquiry(inquiry_id: str, inquiry: dict | None = None, client: Client | None = None, queue: str | None = None) -> dict:
    """Run one inquiry as a workflow. Asking for one already running joins it."""
    tenant = world.current_tenant()
    client = client or await connect()
    return await client.execute_workflow(
        InquiryWorkflow.run, {"tenant": tenant, "inquiry_id": inquiry_id, "inquiry": inquiry},
        id=workflow_id(tenant, inquiry_id), task_queue=queue or queue_for(tenant), id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)


async def decide(case_id: str, user: dict, action: str, note: str = "", signature: dict | None = None,
                 client: Client | None = None) -> dict:
    """Give the reviewer decision to the workflow waiting on this case. With no waiting workflow, there is no decision."""
    tenant = world.current_tenant()
    client = client or await connect()
    args = {"tenant": tenant, "case_id": case_id, "user": user, "action": action, "note": note, "signature": signature}
    try:
        result = await client.get_workflow_handle(review_id(tenant, case_id)).execute_update(ReviewWorkflow.decide, args)
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        raise cases.Denied(f"Case {case_id} is not waiting for a reviewer") from error
    if "denied" in result:
        raise cases.Denied(result["denied"])
    return result["doc"]


async def start_steward(client: Client, queue: str = PLATFORM_QUEUE, poll_seconds: float | None = None) -> None:
    """Make sure the content steward is running. Starting it twice keeps the first one."""
    args = {}
    if poll_seconds is not None:
        args = {"poll_seconds": poll_seconds}
    await client.start_workflow(ContentStewardWorkflow.run, args, id=STEWARD_ID, task_queue=queue,
                                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)


def schedule_id(tenant: str) -> str:
    return f"batch-import-{tenant}"


async def ensure_schedules(client: Client, queue: str | None = None, cron: str = "0 2 * * *") -> None:
    """Set one nightly batch import per tenant at 02:00 UTC. One that exists stays as it is."""
    for tenant in world.tenants():
        action = ScheduleActionStartWorkflow(BatchImportWorkflow.run, {"tenant": tenant["id"]},
                                             id=f"batch-import-run-{tenant['id']}", task_queue=queue or queue_for(tenant["id"]))
        schedule = Schedule(action=action, spec=ScheduleSpec(cron_expressions=[cron]), policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP))
        try:
            await client.create_schedule(schedule_id(tenant["id"]), schedule)
        except ScheduleAlreadyRunningError:
            continue


@contextlib.asynccontextmanager
async def workers(client: Client):
    """One worker per tenant queue, and one for the platform queue."""
    async with contextlib.AsyncExitStack() as stack:
        for queue in [PLATFORM_QUEUE, *(queue_for(tenant["id"]) for tenant in world.tenants())]:
            await stack.enter_async_context(worker(client, queue))
        yield


async def serve() -> None:
    client = await connect()
    async with workers(client):
        await start_steward(client)
        await ensure_schedules(client)
        await asyncio.Event().wait()
