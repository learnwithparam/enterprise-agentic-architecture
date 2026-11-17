"""Arbitrate agents with a supervisor. Two touches reach one doctor in a few days, and policy picks which one stays."""

from hcpagents import supervisor


def touch(pid: str, date: str, promotional: bool) -> dict:
    return {"id": pid, "on": date, "promotional": promotional}


def test_a_doctors_own_need_beats_a_promotion():
    reply = touch("reply", "2026-11-05", promotional=False)
    campaign = touch("campaign", "2026-11-03", promotional=True)
    assert supervisor.arbitrate([reply, campaign]) == {"campaign": "reply"}


def test_between_two_promotions_the_earlier_one_wins():
    first = touch("a", "2026-11-03", promotional=True)
    second = touch("b", "2026-11-04", promotional=True)
    assert supervisor.arbitrate([second, first]) == {"b": "a"}


def test_touches_far_apart_do_not_conflict():
    first = touch("a", "2026-11-03", promotional=True)
    second = touch("b", "2026-11-20", promotional=True)
    assert supervisor.arbitrate([first, second]) == {}


def test_the_answer_does_not_depend_on_the_order_proposals_arrive():
    first = touch("a", "2026-11-03", promotional=True)
    second = touch("b", "2026-11-04", promotional=False)
    third = touch("c", "2026-11-05", promotional=True)
    assert supervisor.arbitrate([first, second, third]) == supervisor.arbitrate([third, first, second])
