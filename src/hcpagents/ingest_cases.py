"""A question from a channel opens a case.

It uses the same start as the seeded inquiries. The case id comes from the row id.
So one event never opens two cases.
"""

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor

from hcpagents import cases, identity, store, world


def case_id(row_id: str) -> str:
    return f"ix-{row_id}"


def inquiry_for(channel: str, row_id: str, record: dict) -> dict:
    """The inquiry the case graph reads. With no doctor, the sender is not a verified professional."""
    return {"id": case_id(row_id), "channel": channel, "hcp": identity.resolve(channel, record["source_id"]),
            "received": record["occurred_at"], "sender": f"{channel} {record['source_id']}", "text": record["text"]}


def open_case(tenant: str, channel: str, row_id: str, record: dict) -> dict | None:
    """Run the case for one question. Give back None when that case already exists."""
    with world.as_tenant(tenant):
        if store.get("mi-cases", case_id(row_id)):
            return None
        inquiry = inquiry_for(channel, row_id, record)
        # A batch import already runs in an event loop. So the case gets its own thread and loop.
        context = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(context.run, asyncio.run, cases.run(inquiry["id"], inquiry)).result()
