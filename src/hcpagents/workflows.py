"""One inquiry as a Temporal workflow. Temporal keeps the only lasting record of where a case is.

This workflow does no input or output. It asks the kernel if each step may run.
A task runs the step. Then it asks the kernel if the facts imply a route.
If the worker dies, another replays this history and goes on from the last finished step (ADR 0016).
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.workflow import ParentClosePolicy

# Tasks are called by name, so this file imports only the kernel.
with workflow.unsafe.imports_passed_through():
    from hcpagents import kernel

STEP_TIMEOUT = timedelta(minutes=5)
RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))
REVIEW_SLA = timedelta(hours=24)  # A draft left too long is escalated, never sent.
CLOSED = ("sent", "rejected")
STEWARD_POLL_S = 5.0  # How often the content steward looks for withdrawn content.
STEWARD_CYCLES = 200  # Passes before the history restarts, so it stays small.


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
        """Takes a tenant and an inquiry id. It may take the inquiry too."""
        tenant, started = args["tenant"], workflow.now()
        doc = await self._activity("open_case", args)
        facts: dict = {}
        trace: list[dict] = []
        out = None
        for node in kernel.ORDER:
            step_start = workflow.now()
            try:
                kernel.check_step(facts, node, self.done)
                result = await self._activity("run_step", {"tenant": tenant, "doc": doc, "node": node})
                doc = result["doc"]
                if "escalated" in result:
                    out = result["escalated"]
                    break
                decision = kernel.advance(facts, self.done, node, result["out"])
            except kernel.KernelViolation as error:
                out = kernel.escalation(error)
                break
            trace.append({"node": node, "ms": (workflow.now() - step_start).total_seconds() * 1000, **result["out"]})
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
        """The case outlives this workflow. A reviewer may take days, so a child waits for them (ADR 0017)."""
        try:
            await workflow.start_child_workflow(
                ReviewWorkflow.run, {"tenant": tenant, "case_id": case_id, "sla_seconds": sla_seconds},
                id=review_id(tenant, case_id), parent_close_policy=ParentClosePolicy.ABANDON)
        except WorkflowAlreadyStartedError:
            pass  # The earlier wait is still open and reads the case as it is now.


@workflow.defn
class ReviewWorkflow:
    """Waits for a person to decide one case. It escalates at the deadline and never decides itself."""

    def __init__(self) -> None:
        self.closed = False
        self.escalated = False
        self.lock = asyncio.Lock()

    @workflow.query
    def status(self) -> dict:
        return {"closed": self.closed, "escalated": self.escalated}

    @workflow.update
    async def decide(self, args: dict) -> dict:
        """Takes the tenant, case, user, action, note and sign off. Cedar decides in the task."""
        async with self.lock:
            result = await workflow.execute_activity("decide_case", args, start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)
            if "doc" in result:
                self.closed = result["doc"]["status"] in CLOSED
            return result

    def _is_closed(self) -> bool:
        return self.closed

    @workflow.run
    async def run(self, args: dict) -> dict:
        """Takes the tenant, the case id and maybe the deadline in seconds."""
        sla = REVIEW_SLA
        if args.get("sla_seconds"):
            sla = timedelta(seconds=args["sla_seconds"])
        try:
            await workflow.wait_condition(self._is_closed, timeout=sla)
        except asyncio.TimeoutError:
            self.escalated = True
            await workflow.execute_activity("escalate_case", {**args, "sla_seconds": sla.total_seconds()},
                                            start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)
            await workflow.wait_condition(self._is_closed)
        await workflow.wait_condition(workflow.all_handlers_finished)
        return {"case": args["case_id"], "escalated": self.escalated}


@workflow.defn
class ContentStewardWorkflow:
    """Always on, one per platform, so nothing goes out on old content.
    It wakes often. It passes pulled content to the steward task and runs the handoff teams.
    Then it restarts its history with continue as new."""

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
            await workflow.execute_activity("handoff_tick", {}, start_to_close_timeout=STEP_TIMEOUT, retry_policy=RETRY)
            await workflow.sleep(timedelta(seconds=args.get("poll_seconds", STEWARD_POLL_S)))
        workflow.continue_as_new(args)


@workflow.defn
class BatchImportWorkflow:
    """The nightly import for one tenant. A Temporal schedule starts it. The activity reads what each channel left in S3."""

    @workflow.run
    async def run(self, args: dict) -> dict:
        return await workflow.execute_activity("import_batch", args, start_to_close_timeout=timedelta(minutes=30), retry_policy=RETRY)
