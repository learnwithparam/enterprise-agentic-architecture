"""Arbitrate agents with a supervisor: two touches to one doctor in a few days, and policy decides which stays."""

from hcpagents import supervisor


def touch(pid: str, on: str, promotional: bool) -> dict:
    return {"id": pid, "on": on, "promotional": promotional}


def test_a_doctors_own_need_beats_a_promotion():
    reply = touch("reply", "2026-11-05", promotional=False)
    campaign = touch("campaign", "2026-11-03", promotional=True)
    assert supervisor.arbitrate([reply, campaign]) == {"campaign": "reply"}


def test_between_two_promotions_the_earlier_one_wins():
    a = touch("a", "2026-11-03", promotional=True)
    b = touch("b", "2026-11-04", promotional=True)
    assert supervisor.arbitrate([b, a]) == {"b": "a"}


def test_touches_far_apart_do_not_conflict():
    a = touch("a", "2026-11-03", promotional=True)
    b = touch("b", "2026-11-20", promotional=True)
    assert supervisor.arbitrate([a, b]) == {}


def test_the_answer_does_not_depend_on_the_order_proposals_arrive():
    a = touch("a", "2026-11-03", promotional=True)
    b = touch("b", "2026-11-04", promotional=False)
    c = touch("c", "2026-11-05", promotional=True)
    assert supervisor.arbitrate([a, b, c]) == supervisor.arbitrate([c, a, b])
