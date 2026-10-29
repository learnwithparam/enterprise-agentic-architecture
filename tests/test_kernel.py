"""No plan may break the kernel. These drive kernel.run with nodes that misbehave and expect a refusal."""

import asyncio

import pytest

from hcpagents import graph, kernel


def impls(**override):
    """Honest nodes that set the safe value of every fact, with some replaced by misbehaving ones."""
    safe = {"ae": False, "verified_hcp": True, "injection": False, "intent": "medical_question", "known_product": True,
            "in_scope": True, "covered": True, "grounded": True, "auto_allowed": True}

    def honest(produces):
        async def node(_ctx):
            return {"facts": {f: safe[f] for f in produces}}
        return node

    nodes = {name: honest(produces) for name, produces in graph.NODES}
    return nodes | override


def run(nodes):
    return asyncio.run(kernel.run(nodes, {}))


def test_honest_nodes_reach_a_send():
    assert run(impls())["decision"]["route"] == "send"


def test_a_step_cannot_run_after_the_case_is_routed():
    assert kernel.check_step({"ae": False, "verified_hcp": True}, "safety_screen", ["intake"]) is None
    with pytest.raises(kernel.KernelViolation, match="already routed to pv"):
        kernel.check_step({"verified_hcp": True, "ae": True}, "classify", ["intake", "safety_screen"])


def test_the_safety_screen_cannot_be_skipped():
    with pytest.raises(kernel.KernelViolation, match="next step is safety_screen"):
        kernel.check_step({"verified_hcp": True}, "classify", ["intake"])


def test_a_step_cannot_repeat_or_be_invented():
    with pytest.raises(kernel.KernelViolation):
        kernel.check_step({"verified_hcp": True}, "intake", ["intake"])
    with pytest.raises(kernel.KernelViolation, match="not a kernel step"):
        kernel.check_step({}, "send_now", [])


def test_a_late_step_cannot_rewrite_the_adverse_event_fact():
    async def rewrites(_ctx):
        return {"facts": {"covered": True, "ae": False}}
    with pytest.raises(kernel.KernelViolation, match="must set exactly"):
        run(impls(assemble=rewrites))


def test_a_step_that_forgets_its_fact_is_refused():
    async def silent(_ctx):
        return {"facts": {}}
    with pytest.raises(kernel.KernelViolation):
        run(impls(safety_screen=silent))


def test_a_route_the_facts_do_not_imply_is_refused():
    facts = {"ae": True}
    for route in ("send", "review", "decline"):
        with pytest.raises(kernel.KernelViolation, match="imply pv"):
            kernel.check_route(facts, route)
    assert kernel.check_route(facts, "pv")["route"] == "pv"


def test_no_route_can_be_chosen_before_the_facts_exist():
    with pytest.raises(kernel.KernelViolation, match="no route can be chosen yet"):
        kernel.check_route({}, "send")


def test_an_adverse_event_stops_the_run_before_any_drafting_step():
    ran = []

    def spy(name, facts):
        async def node(_ctx):
            ran.append(name)
            return {"facts": facts}
        return node
    out = run(impls(safety_screen=spy("safety_screen", {"ae": True}), assemble=spy("assemble", {"covered": True})))
    assert out["decision"]["route"] == "pv" and "assemble" not in ran


@pytest.mark.floci
def test_a_case_whose_plan_breaks_the_kernel_goes_to_a_human_and_sends_nothing(monkeypatch):
    from hcpagents import cases, infra, world

    infra.provision(reset=True)

    async def broken(_nodes, _ctx):
        raise kernel.KernelViolation("assemble tried to set ae")
    monkeypatch.setattr(cases, "run_graph", broken)
    d = asyncio.run(cases.run(world.inquiries()[0]["id"]))
    assert d["route"] == "review" and d["decision"]["rule"] == "kernel_violation" and d["status"] != "sent"
