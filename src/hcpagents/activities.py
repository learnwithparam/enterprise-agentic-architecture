"""The parts of a case that change things, one Temporal task each. The workflow decides and these act.

Each task gets the tenant and runs inside it. It rebuilds the case from its saved copy.
So a step can run on any worker after any crash (ADR 0016).
"""

from temporalio import activity
from temporalio.exceptions import ApplicationError

from hcpagents import agents, cases, handoff_workers, ingest, world
from hcpagents.kernel import ORDER, KernelViolation, escalation


@activity.defn
async def open_case(args: dict) -> dict:
    with world.as_tenant(args["tenant"]):
        return cases.begin(args.get("inquiry") or world.inquiry(args["inquiry_id"])).doc


@activity.defn
async def run_step(args: dict) -> dict:
    """Run one kernel step. If no model is left or the kernel refuses the plan, the case goes to review."""
    node = args["node"]
    if node not in ORDER:
        raise ApplicationError(f"{node} is not a kernel step", non_retryable=True)
    with world.as_tenant(args["tenant"]):
        case = cases.restore(args["doc"])
        try:
            return {"doc": case.doc, "out": await getattr(case, node)({})}
        except (agents.EscalateToHuman, KernelViolation) as error:
            return {"doc": case.doc, "escalated": escalation(error)}


@activity.defn
async def steward_tick(_args: dict) -> dict:
    """One pass of the content steward. It handles each withdrawn content event waiting on the queue."""
    return cases.process_invalidations()


@activity.defn
async def handoff_tick(_args: dict) -> dict:
    """One pass of the handoff teams. Each event names its tenant, so one pass serves every tenant."""
    return handoff_workers.run_once()


@activity.defn
async def close_case(args: dict) -> dict:
    with world.as_tenant(args["tenant"]):
        return cases.finish(cases.restore(args["doc"]), args["out"], args["latency_ms"])


@activity.defn
async def decide_case(args: dict) -> dict:
    """Approve or reject, as a reviewer chose. A refusal is an answer, not a failure."""
    with world.as_tenant(args["tenant"]):
        try:
            if args["action"] == "approve":
                return {"doc": cases.approve(args["case_id"], args["user"], args.get("signature"))}
            return {"doc": cases.reject(args["case_id"], args["user"], args.get("note") or "No reason given")}
        except cases.Denied as error:
            return {"denied": str(error)}


@activity.defn
async def escalate_case(args: dict) -> dict:
    with world.as_tenant(args["tenant"]):
        return cases.escalate(args["case_id"], args["sla_seconds"])


@activity.defn
async def import_batch(args: dict) -> dict:
    """Ingest the batch files waiting for one tenant. Running it twice is safe."""
    return ingest.import_batch(args["tenant"])
