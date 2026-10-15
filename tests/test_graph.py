"""The routing table is the policy. These walk every combination of facts."""

import pytest

from hcpagents import graph


def test_an_adverse_event_always_goes_to_pharmacovigilance():
    for facts in graph.every_fact_combination():
        if facts["ae"]:
            assert graph.decide(facts)["route"] == "pv", facts


def test_an_injection_attempt_from_a_verified_hcp_is_declined():
    for facts in graph.every_fact_combination():
        if facts["injection"] and facts["verified_hcp"] and not facts["ae"]:
            assert graph.decide(facts)["route"] == "decline", facts


def test_send_needs_every_safety_fact_true():
    for facts in graph.every_fact_combination():
        if graph.decide(facts)["route"] == "send":
            assert facts["intent"] == "medical_question"
            assert not facts["ae"] and not facts["injection"]
            assert all(facts[k] for k in ("verified_hcp", "known_product", "in_scope", "covered", "grounded", "auto_allowed"))


def test_an_unknown_fact_waits_instead_of_guessing():
    assert graph.decide({}) is None
    assert graph.decide({"ae": False}) is None
    assert graph.decide({"ae": True})["route"] == "pv"


def test_every_routing_fact_is_established_by_a_node():
    produced = {f for _, facts in graph.NODES for f in facts}
    assert {f for f, *_ in graph.ROUTING} == produced == set(graph.FACTS)


def _one_case_per_rule():
    base = {"ae": False, "verified_hcp": True, "injection": False, "intent": "medical_question", "known_product": True,
            "in_scope": True, "covered": True, "grounded": True, "auto_allowed": True}
    yield base
    for fact, value, _, _ in graph.ROUTING:
        yield base | {fact: value}
    yield {"ae": False}


@pytest.mark.floci
def test_step_functions_on_floci_route_like_python():
    import json
    import time

    from hcpagents.aws import client
    from hcpagents.infra import machine

    sfn, arn = client("stepfunctions"), machine()
    for facts in _one_case_per_rule():
        ex = sfn.start_execution(stateMachineArn=arn, input=json.dumps({"facts": facts}))["executionArn"]
        for _ in range(100):
            d = sfn.describe_execution(executionArn=ex)
            if d["status"] != "RUNNING":
                break
            time.sleep(0.05)
        assert d["status"] == "SUCCEEDED"
        py = graph.decide(facts)
        got = json.loads(d["output"])
        assert got == ({"route": py["route"], "rule": py["rule"]} if py else {"route": None, "rule": None}), facts
