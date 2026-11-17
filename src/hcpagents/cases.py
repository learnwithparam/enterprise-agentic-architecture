"""One inquiry becomes one case. The run function walks the graph, then hands the case on.

The human decisions live in case_review. Cedar allows each one and the ledger records it.
"""

import time
from datetime import UTC, datetime

from hcpagents import agents, authz, observe, releases, store, tracing, world
from hcpagents.case_core import Case, autonomy_setting, restore, save_autonomy, untrusted_header
from hcpagents.case_review import (Denied, approve, erase_person, escalate, process_invalidations, reject, set_autonomy,
                                   withdraw)
from hcpagents.case_send import STATUS, handoff
from hcpagents.case_send import now as _now
from hcpagents.case_send import sha as _sha
from hcpagents.kernel import ORDER, KernelViolation, escalation
from hcpagents.kernel import run as run_graph

__all__ = [
    "Case", "Denied", "ORDER", "STATUS", "approve", "autonomy_setting", "begin", "erase_person", "escalate", "finish",
    "process_invalidations", "reject", "restore", "run", "save_autonomy", "set_autonomy", "untrusted_header", "visible",
    "withdraw", "_now",
]


def begin(inquiry: dict) -> Case:
    """Open a case for an inquiry and note that it came in."""
    case = Case(inquiry)
    case.audit({"type": "case_received", "channel": inquiry["channel"], "text_sha256": _sha(inquiry["text"])})
    return case


def visible(doc: dict, user: dict) -> dict:
    """The case as this user may see it, whole or only that it exists."""
    allowed, why = authz.user_can(user, "ViewCaseDetail", "Case", doc["id"], {"country": doc["country"], "route": doc["route"]})
    if allowed:
        return doc
    keep = ("id", "route", "status", "country", "product", "created_at")
    return {key: doc.get(key) for key in keep} | {"redacted": why, "inquiry": {"id": doc["id"], "channel": doc["inquiry"]["channel"]}}


def finish(case: Case, out: dict, latency_ms: int) -> dict:
    """Record the route, perform its handoff and store the case."""
    doc = case.doc
    doc |= {"decision": out["decision"], "facts": out["facts"], "route": out["decision"]["route"],
            "nodes": [dict(step) for step in out["trace"]], "latency_ms": latency_ms,
            "cost_usd": round(sum(call["cost_usd"] for call in doc["agent_calls"]), 6),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"), "history": [], "release": releases.current()}
    if doc["route"] not in ("send", "review"):
        doc["draft"] = None  # No AI text exists for cases the AI must not answer.
    case.audit({"type": "routed", "route": doc["route"], "rule": doc["decision"]["rule"], "facts": doc["facts"]})
    handoff(case)
    store.put("mi-cases", doc)
    observe.metrics(doc)
    observe.log(doc)
    tracing.export_case(doc)
    return doc


async def run(inquiry_id: str, inquiry: dict | None = None) -> dict:
    """The whole case in this process. The Temporal workflow runs the same steps, one task each."""
    case = begin(inquiry or world.inquiry(inquiry_id))
    start = time.perf_counter()
    try:
        out = await run_graph({name: getattr(case, name) for name in ORDER}, {})
    except (agents.EscalateToHuman, KernelViolation) as error:
        out = escalation(error)
    return finish(case, out, round((time.perf_counter() - start) * 1000))
