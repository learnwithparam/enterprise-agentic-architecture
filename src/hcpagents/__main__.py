"""uv run python -m hcpagents run <inquiry-id|all>    run inquiries (replay; LIVE=1 records)"""

import asyncio
import sys

from hcpagents import agents, cases, world


async def main(target: str) -> None:
    ids = [i["id"] for i in world.inquiries()] if target == "all" else [target]
    for i in ids:
        d = await cases.run(i)
        inq = world.inquiry(i)
        ok = d["route"] == inq["expect"] or d["route"] in inq.get("also_safe", [])
        print(f"{i:22} {d['route']:11} expect {inq['expect']:11} {'ok ' if ok else 'MISS'} ${d['cost_usd']:.5f} {d['mode']}")
    if agents.live():
        print(f"live spend this run: ${agents.SPEND.session:.5f}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "run":
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[2]))
