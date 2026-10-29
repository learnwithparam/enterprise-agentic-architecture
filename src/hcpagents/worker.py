"""The worker process: `uv run python -m hcpagents.worker`."""

import asyncio

from hcpagents import world
from hcpagents.durable import serve

if __name__ == "__main__":
    world.load_env()
    asyncio.run(serve())
