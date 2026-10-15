"""Gate releases with evals: one missed adverse event, one unsafe send or one other model fails the release."""

from hcpagents import agents, evals


def row(case, expect, route, also_safe=(), models=(agents.MODEL,)):
    return {"id": case, "expect": expect, "route": route, "also_safe": list(also_safe),
            "acceptable": route == expect or route in also_safe, "ungrounded": 0, "cost_usd": 0.001,
            "models": list(models)}


GOOD = [row("a", "send", "send"), row("b", "pv", "pv"), row("c", "review", "review")]


def failures(rows):
    return evals.gate(evals.score(rows))


def test_a_clean_run_passes():
    assert failures(GOOD) == []


def test_one_missed_adverse_event_fails_the_release():
    assert any(f.startswith("ae_recall") for f in failures([GOOD[0], row("b", "pv", "review"), GOOD[2]]))


def test_a_more_cautious_route_is_allowed():
    assert failures([*GOOD, row("d", "review", "specialist", also_safe=["specialist"])]) == []


def test_sending_what_a_human_should_review_fails_the_release():
    assert any(f.startswith("unsafe_auto_sends") for f in failures([*GOOD, row("e", "review", "send")]))


def test_a_call_on_another_model_fails_the_release():
    assert any(f.startswith("non_haiku_calls") for f in failures([*GOOD, row("f", "send", "send", models=["claude-haiku-4-5"])]))
