"""Cap model calls per case and per tenant day. A refusal says which cap and makes no call."""

from hcpagents import agent_caps, store


def runs(count: int, attempts: int = 1) -> list[dict]:
    return [{"agent": "assembler", "attempts": attempts} for _ in range(count)]


def use_day_total(monkeypatch, total: int) -> None:
    def get(table, doc_id):
        return {"id": doc_id, "calls": total}

    monkeypatch.setattr(store, "get", get)


def test_a_case_under_every_cap_may_call(monkeypatch):
    use_day_total(monkeypatch, 0)
    assert agent_caps.check(runs(2)) is None


def test_a_case_at_the_hop_cap_is_refused(monkeypatch):
    use_day_total(monkeypatch, 0)
    assert "hop cap" in agent_caps.check(runs(agent_caps.MAX_HOPS))


def test_retries_count_as_calls(monkeypatch):
    use_day_total(monkeypatch, 0)
    assert "case cap" in agent_caps.check(runs(2, attempts=agent_caps.MAX_CALLS_PER_CASE // 2))


def test_a_tenant_at_the_day_cap_is_refused(monkeypatch):
    use_day_total(monkeypatch, agent_caps.TENANT_CALLS_PER_DAY)
    assert "day cap" in agent_caps.check(runs(1))


def test_the_caps_leave_room_for_the_longest_honest_case():
    assert agent_caps.MAX_HOPS >= 5 and agent_caps.MAX_CALLS_PER_CASE >= 10
