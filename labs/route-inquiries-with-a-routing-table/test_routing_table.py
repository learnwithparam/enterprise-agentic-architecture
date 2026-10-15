"""Route inquiries with a routing table: the order of the rows is the policy, and an unknown fact waits."""

from hcpagents import graph

SAFE = {"ae": False, "verified_hcp": True, "injection": False, "intent": "medical_question", "known_product": True,
        "in_scope": True, "covered": True, "grounded": True, "auto_allowed": True}


def test_every_fact_true_sends():
    assert graph.decide(SAFE)["route"] == "send"


def test_an_adverse_event_inside_an_injection_still_reaches_pharmacovigilance():
    assert graph.decide(SAFE | {"ae": True, "injection": True})["route"] == "pv"


def test_any_one_fact_going_wrong_stops_the_send():
    wrong = {"ae": True, "verified_hcp": False, "injection": True, "intent": "other", "known_product": False,
             "in_scope": False, "covered": False, "grounded": False, "auto_allowed": False}
    for fact, value in wrong.items():
        assert graph.decide(SAFE | {fact: value})["route"] != "send", fact


def test_the_engine_waits_for_a_fact_instead_of_guessing():
    assert graph.decide({k: v for k, v in SAFE.items() if k != "grounded"}) is None


def test_the_step_functions_definition_comes_from_the_same_table():
    states = graph.asl()["States"]
    assert {f"Route{i}" for i in range(len(graph.ROUTING))} | {"Send"} <= set(states)
