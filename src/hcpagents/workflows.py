"""One inquiry as a Temporal workflow. Temporal's history is the only durable record of where a case is.

The workflow is deterministic and does no I/O. It asks the kernel whether each step may run, has an
activity run it, and asks the kernel again whether the facts imply a route. If the worker dies, another
replays this history and continues from the last finished step (ADR 0016).
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.workflow import ParentClosePolicy

# Activities are called by name, so this module imports only the pure kernel.
with workflow.unsafe.imports_passed_through():
    from hcpagents import kernel

STEP_TIMEOUT = timedelta(minutes=5)
RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))
REVIEW_SLA = timedelta(hours=24)  # a draft nobody has decided in this long is escalated, never sent
CLOSED = ("sent", "rejected")
STEWARD_POLL_S = 5.0  # how often the content steward looks for withdrawn content
STEWARD_CYCLES = 200  # passes before the history is rolled over, so an always-on workflow never grows without bound


def review_id(tenant: str, case_id: str) -> str:
    return f"review-{tenant}-{case_id}"


@workflow.defn
class InquiryWorkflow:
    def __init__(self) -> None:
        self.done: list[str] = []

    @workflow.query
    def progress(self) -> list[str]:
        return self.done

    async def _activity(self, name: str, arg: dict) -> dict:
        return await workflow.execute_activity(name, arg, start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)

    @workflow.run
    async def run(self, args: dict) -> dict:
        """args: tenant, inquiry_id, and optionally the inquiry itself (a typed question has no file)."""
        tenant, started = args["tenant"], workflow.now()
        doc = await self._activity("open_case", args)
        facts: dict = {}
        trace: list[dict] = []
        out = None
        for node in kernel.ORDER:
            step_start = workflow.now()
            try:
                kernel.check_step(facts, node, self.done)
                res = await self._activity("run_step", {"tenant": tenant, "doc": doc, "node": node})
                doc = res["doc"]
                if "escalated" in res:
                    out = res["escalated"]
                    break
                decision = kernel.advance(facts, self.done, node, res["out"])
            except kernel.KernelViolation as e:
                out = kernel.escalation(e)
                break
            trace.append({"node": node, "ms": (workflow.now() - step_start).total_seconds() * 1000, **res["out"]})
            if decision:
                out = {"decision": decision, "facts": facts, "trace": trace}
                break
        if out is None:
            raise RuntimeError("graph finished without a decision")
        latency_ms = round((workflow.now() - started).total_seconds() * 1000)
        doc = await self._activity("close_case", {"tenant": tenant, "doc": doc, "out": out, "latency_ms": latency_ms})
        if doc["status"] == "awaiting_review":
            await self._hand_to_reviewers(tenant, doc["id"], args.get("review_sla_seconds"))
        return doc

    async def _hand_to_reviewers(self, tenant: str, case_id: str, sla_seconds: float | None) -> None:
        """The case outlives this workflow: a reviewer may take days, so a child waits for them (ADR 0017)."""
        try:
            await workflow.start_child_workflow(
                ReviewWorkflow.run, {"tenant": tenant, "case_id": case_id, "sla_seconds": sla_seconds},
                id=review_id(tenant, case_id), parent_close_policy=ParentClosePolicy.ABANDON)
        except WorkflowAlreadyStartedError:
            pass  # the earlier wait is still open and reads the case as it is now


@workflow.defn
class ReviewWorkflow:
    """Waits for a human decision on one case. It escalates at the SLA and never decides anything itself."""

    def __init__(self) -> None:
        self.closed = False
        self.escalated = False
        self.lock = asyncio.Lock()

    @workflow.query
    def status(self) -> dict:
        return {"closed": self.closed, "escalated": self.escalated}

    @workflow.update
    async def decide(self, args: dict) -> dict:
        """args: tenant, case_id, user, action (approve or reject), note, signature. Cedar decides inside the activity."""
        async with self.lock:
            res = await workflow.execute_activity("decide_case", args, start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)
            if "doc" in res:
                self.closed = res["doc"]["status"] in CLOSED
            return res

    @workflow.run
    async def run(self, args: dict) -> dict:
        """args: tenant, case_id, and optionally sla_seconds."""
        sla = timedelta(seconds=args["sla_seconds"]) if args.get("sla_seconds") else REVIEW_SLA
        try:
            await workflow.wait_condition(lambda: self.closed, timeout=sla)
        except asyncio.TimeoutError:
            self.escalated = True
            await workflow.execute_activity("escalate_case", {**args, "sla_seconds": sla.total_seconds()},
                                            start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)
            await workflow.wait_condition(lambda: self.closed)
        await workflow.wait_condition(workflow.all_handlers_finished)
        return {"case": args["case_id"], "escalated": self.escalated}


@workflow.defn
class ContentStewardWorkflow:
    """Always on, one per platform: nothing goes out on stale content. It wakes every few seconds, hands the
    withdrawn-content events to the steward activity, and rolls its history over with continue-as-new."""

    def __init__(self) -> None:
        self.invalidated = 0

    @workflow.query
    def handled(self) -> int:
        return self.invalidated

    @workflow.run
    async def run(self, args: dict) -> None:
        for _ in range(STEWARD_CYCLES):
            out = await workflow.execute_activity("steward_tick", {}, start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)
            self.invalidated += len(out["cases"])
            await workflow.sleep(timedelta(seconds=args.get("poll_seconds", STEWARD_POLL_S)))
        workflow.continue_as_new(args)


@workflow.defn
class BatchImportWorkflow:
    """The nightly import for one tenant. A Temporal schedule starts it; the activity reads what each channel dropped in S3."""

    @workflow.run
    async def run(self, args: dict) -> dict:
        return await workflow.execute_activity("import_batch", args, start_to_close_timeout=timedelta(minutes=30), retry_policy=RETRY)
