"""The kernel holds what no agent plan may do (ADR 0013).

Agents choose how to do a step. The kernel owns which steps exist and their order.
It also owns which facts each step may set, and the route those facts imply.
It checks every step before it runs and every route before it is returned.
So a plan that skips the safety screen or reopens a decided case is refused, not trusted.
"""

import time
from collections.abc import Awaitable, Callable

from hcpagents import graph

Node = Callable[[dict], Awaitable[dict]]
ORDER = [name for name, _ in graph.NODES]
PRODUCES = dict(graph.NODES)


class KernelViolation(Exception):
    """A plan tried something the kernel does not allow. The case goes to a person."""


def check_step(facts: dict, node: str, done: list[str]) -> None:
    """May this step run now? Only the next step in order, and only while no route is set."""
    decided = graph.decide(facts)
    if decided:
        raise KernelViolation(f"{node}: the case is already routed to {decided['route']}; no further step may run")
    if node not in PRODUCES:
        raise KernelViolation(f"{node} is not a kernel step")
    if node != ORDER[len(done)]:
        raise KernelViolation(f"{node} cannot run now; the next step is {ORDER[len(done)]}")


def check_facts(node: str, facts: dict) -> None:
    """A step may set exactly the facts it is meant to make. A late step cannot rewrite an early one."""
    allowed = set(PRODUCES[node])
    if set(facts) != allowed:
        raise KernelViolation(f"{node} must set exactly {sorted(allowed)}, not {sorted(facts)}")


def check_attempt(attempt: int, limit: int) -> None:
    """A plan loop has a limit. The last attempt is the limit."""
    if attempt > limit:
        raise KernelViolation(f"attempt {attempt} is over the limit of {limit}")


def check_route(facts: dict, route: str) -> dict:
    """Return the route the facts imply. Any other route is a violation."""
    decided = graph.decide(facts)
    if decided is None:
        raise KernelViolation(f"no route can be chosen yet; facts known: {sorted(facts)}")
    if decided["route"] != route:
        raise KernelViolation(f"the facts imply {decided['route']}, not {route}")
    return decided


def escalation(error: Exception) -> dict:
    """No model is left, or a plan broke the kernel, so a person decides. Nothing is drafted or sent."""
    rule = "router_escalated"
    if isinstance(error, KernelViolation):
        rule = "kernel_violation"
    return {"decision": {"route": "review", "rule": rule, "why": str(error)}, "facts": {}, "trace": []}


def advance(facts: dict, done: list[str], node: str, out: dict) -> dict | None:
    """Record a finished step. Return the decision once the facts imply a route, else None."""
    check_facts(node, out["facts"])
    facts.update(out["facts"])
    done.append(node)
    decision = graph.decide(facts)
    if decision:
        check_route(facts, decision["route"])
    return decision


async def run(impls: dict[str, Node], context: dict) -> dict:
    """Run steps in order until a route is set. Each step returns its facts and some detail."""
    facts: dict = {}
    trace: list[dict] = []
    done: list[str] = []
    for name in ORDER:
        check_step(facts, name, done)
        start = time.perf_counter()
        out = await impls[name](context)
        context.setdefault("facts", {}).update(out["facts"])
        decision = advance(facts, done, name, out)
        trace.append({"node": name, "ms": round((time.perf_counter() - start) * 1000, 1), **out})
        if decision:
            return {"decision": decision, "facts": facts, "trace": trace}
    raise RuntimeError("graph finished without a decision")
