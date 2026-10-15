"""Pin the model with Agent SDK options: one model, nothing loaded from the developer's machine, a bill we compute."""

import pytest

from hcpagents import agents

CASE = {"id": "lab-pin", "country": "DE", "product": "VEL"}


def test_every_agent_runs_on_haiku_5_5_and_loads_nothing_local():
    for name in agents.AGENTS:
        o = agents._options(name, CASE, {}, None, None, [])
        assert o.model == "claude-haiku-5-5"
        assert o.setting_sources == [] and o.plugins == [] and o.strict_mcp_config
        assert o.env["ANTHROPIC_SMALL_FAST_MODEL"] == o.model


def test_a_result_that_used_another_model_is_refused():
    with pytest.raises(agents.ModelPolicyError):
        agents.check_models({"claude-haiku-5-5": {}, "claude-sonnet-5-5": {}})


def test_changing_the_system_prompt_needs_a_new_recording(monkeypatch):
    before = agents.recording_key("triage", "same message")
    monkeypatch.setitem(agents.AGENTS["triage"], "system", agents.AGENTS["triage"]["system"] + " Be brief.")
    assert agents.recording_key("triage", "same message") != before


def test_the_bill_is_computed_from_tokens():
    assert agents.cost_usd({"input_tokens": 2_000, "output_tokens": 500}) == pytest.approx(0.00045)
