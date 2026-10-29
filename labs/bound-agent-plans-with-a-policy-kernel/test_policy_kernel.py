"""Bound agent plans with a policy kernel: a plan cannot skip a step, rewrite a fact or loop forever."""

import pytest

from hcpagents import kernel


def test_a_step_cannot_run_out_of_order():
    first, second = kernel.ORDER[0], kernel.ORDER[1]
    kernel.check_step({}, first, [])
    with pytest.raises(kernel.KernelViolation):
        kernel.check_step({}, second, [])


def test_a_name_that_is_not_a_step_is_refused():
    with pytest.raises(kernel.KernelViolation):
        kernel.check_step({}, "send_now", [])


def test_a_step_may_set_only_the_facts_it_declares():
    node = kernel.ORDER[0]
    declared = {fact: False for fact in kernel.PRODUCES[node]}
    kernel.check_facts(node, declared)
    with pytest.raises(kernel.KernelViolation):
        kernel.check_facts(node, declared | {"grounded": True})


def test_a_plan_loop_is_bounded():
    kernel.check_attempt(3, 3)
    with pytest.raises(kernel.KernelViolation):
        kernel.check_attempt(4, 3)


def test_a_violation_fails_closed_to_a_person():
    out = kernel.escalation(kernel.KernelViolation("skipped the screen"))
    assert out["decision"]["route"] == "review"
    assert out["decision"]["rule"] == "kernel_violation"
