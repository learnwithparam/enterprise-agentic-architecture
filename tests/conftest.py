"""A case and a reviewer's wait are Temporal workflows that outlive a test, so each test starts with none open."""

import asyncio

import pytest


async def _stop_open_workflows() -> None:
    from hcpagents import durable
    client = await durable.connect()
    async for w in client.list_workflows('ExecutionStatus="Running"'):
        if w.id.startswith("temporal-sys-"):
            continue  # a schedule's own workflow
        await client.get_workflow_handle(w.id).terminate("test cleanup")


@pytest.fixture(autouse=True)
def no_open_workflows(request):
    if request.node.get_closest_marker("floci"):
        asyncio.run(_stop_open_workflows())
    yield
