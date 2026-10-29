"""The side-effecting pieces of a case, one Temporal activity each. The workflow decides; these do.

Every activity takes the tenant, runs inside it, and rebuilds the case from its document, so a step can
run on any worker after any crash (ADR 0016).
"""

from temporalio import activity
from temporalio.exceptions import ApplicationError

from hcpagents import agents, cases, ingest, world
from hcpagents.kernel import ORDER, KernelViolation, escalation


@activity.defn
async def open_case(args: dict) -> dict:
    with world.as_tenant(args["tenant"]):
        return cases.begin(args.get("inquiry") or world.inquiry(args["inquiry_id"])).doc


@activity.defn
async def run_step(args: dict) -> dict:
    """One kernel step. A model with nothing left to try, or a plan the kernel refuses, ends the case in review."""
    node = args["node"]
    if node not in ORDER:
        raise ApplicationError(f"{node} is not a kernel step", non_retryable=True)
    with world.as_tenant(args["tenant"]):
        c = cases.restore(args["doc"])
        try:
            return {"doc": c.doc, "out": await getattr(c, node)({})}
        except (agents.EscalateToHuman, KernelViolation) as e:
            return {"doc": c.doc, "escalated": escalation(e)}


@activity.defn
async def steward_tick(_args: dict) -> dict:
    """One pass of the content steward: handle every content-withdrawn event waiting on the queue."""
    return cases.process_invalidations()


@activity.defn
async def close_case(args: dict) -> dict:
    with world.as_tenant(args["tenant"]):
        return cases.finish(cases.restore(args["doc"]), args["out"], args["latency_ms"])


@activity.defn
async def decide_case(args: dict) -> dict:
    """A reviewer's approve or reject. Cedar and the signature check run in cases; a refusal is an answer, not a failure."""
    with world.as_tenant(args["tenant"]):
        try:
            if args["action"] == "approve":
                return {"doc": cases.approve(args["case_id"], args["user"], args.get("signature"))}
            return {"doc": cases.reject(args["case_id"], args["user"], args.get("note") or "No reason given")}
        except cases.Denied as e:
            return {"denied": str(e)}


@activity.defn
async def escalate_case(args: dict) -> dict:
    with world.as_tenant(args["tenant"]):
        return cases.escalate(args["case_id"], args["sla_seconds"])


@activity.defn
async def import_batch(args: dict) -> dict:
    """Ingest the batch files waiting for one tenant. Re-running it is safe: ingestion is idempotent."""
    return ingest.import_batch(args["tenant"])
