"""Pick the model with a router: Haiku by default, Sonnet when the work or a failure asks for it, then a person."""

import pytest

from hcpagents import router
from hcpagents.router import HAIKU, SONNET, Outcome


def test_high_volume_work_stays_on_haiku():
    for task in ("screen", "classify", "select"):
        assert router.route(task).model == HAIKU, task


def test_open_ended_work_goes_to_sonnet():
    for task in ("plan", "arbitrate", "synthesize", "optimize"):
        assert router.route(task).model == SONNET, task


def test_a_schema_failure_escalates_once_to_sonnet():
    tried = (Outcome(HAIKU, router.SCHEMA_FAILURE),)
    assert router.route("select", prior=tried).model == SONNET


def test_when_sonnet_also_fails_a_person_takes_it():
    tried = (Outcome(HAIKU, router.SCHEMA_FAILURE), Outcome(SONNET, router.SCHEMA_FAILURE))
    assert router.route("select", prior=tried).model is None


def test_a_case_with_no_budget_left_goes_to_a_person_instead_of_spending():
    assert router.route("plan", budget_left_usd=0.001).model is None


def test_the_router_never_returns_a_model_outside_the_two_allowed():
    for task in router.HAIKU_TASKS | router.SONNET_TASKS:
        for risk in router.RISKS:
            assert router.route(task, risk).model in {HAIKU, SONNET}


def test_an_unknown_task_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        router.route("chat")
