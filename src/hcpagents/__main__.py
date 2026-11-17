"""uv run python -m hcpagents run <inquiry-id|all>

This runs the inquiries. Set LIVE=1 to record them.
"""

import asyncio
import sys

from hcpagents import agents, cases, evals, gateway, world


def _is_safe(case: dict, inquiry: dict) -> bool:
    return case["route"] == inquiry["expect"] or case["route"] in inquiry.get("also_safe", [])


async def main(target: str) -> None:
    if target == "all":
        ids = [inquiry["id"] for inquiry in world.inquiries()]
    else:
        ids = [target]
    for inquiry_id in ids:
        case = await cases.run(inquiry_id)
        inquiry = world.inquiry(inquiry_id)
        verdict = "MISS"
        if _is_safe(case, inquiry):
            verdict = "ok "
        print(f"{inquiry_id:22} {case['route']:11} expect {inquiry['expect']:11} {verdict} ${case['cost_usd']:.5f} {case['mode']}")
    if agents.live():
        print(f"live spend this run: ${agents.SPEND.session:.5f}")
        if target == "all":
            evals.write_evidence(await evals.inquiry_keys())


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "run":
        sys.exit(__doc__)
    with gateway.for_live_calls():
        asyncio.run(main(sys.argv[2]))
