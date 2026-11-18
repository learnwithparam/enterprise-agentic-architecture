"""Live labs 10 and 11. The model reads a thread that fits a token budget. The oldest turns go first."""

import asyncio

import pytest

from hcpagents import agent_context, agents, kernel
from tests.live_g_support import INQUIRY, install


def turn(who: str, words: int) -> dict:
    return {"from": who, "text": " ".join(["word"] * words)}


def test_a_token_count_is_never_below_a_quarter_of_the_characters():
    text = "Veltrona is taken once a day with food."
    assert agent_context.count_tokens(text) >= len(text) / 4


def test_a_thread_over_the_budget_loses_its_oldest_turns_first():
    thread = [turn("a", 40), turn("b", 40), turn("c", 40), turn("d", 40)]
    fitted = agent_context.fit_thread(thread, "Where is it stored?", budget=130)
    assert [t["from"] for t in fitted["kept"]] == ["c", "d"] and fitted["dropped"] == 2
    assert fitted["tokens"] <= 130


def test_the_question_and_the_newest_turn_always_stay():
    thread = [turn("a", 40), turn("b", 40)]
    fitted = agent_context.fit_thread(thread, "Where is it stored?", budget=75)
    assert [t["from"] for t in fitted["kept"]] == ["b"]


def test_a_thread_that_fits_is_kept_whole():
    thread = [turn("a", 5), turn("b", 5)]
    assert agent_context.fit_thread(thread, "Q?")["dropped"] == 0


def test_an_inquiry_without_a_thread_reaches_the_model_unchanged():
    text, note = agent_context.model_text({"text": "Where is it stored?"})
    assert text == "Where is it stored?" and note["dropped"] == 0


def test_a_question_too_big_for_the_budget_goes_to_a_person_not_cut():
    with pytest.raises(agent_context.ContextTooLarge) as caught:
        agent_context.fit_thread([turn("a", 5)], " ".join(["word"] * 400), budget=100)
    assert isinstance(caught.value, agents.EscalateToHuman)
    out = kernel.escalation(caught.value)
    assert out["decision"]["route"] == "review" and out["decision"]["rule"] == "context_too_large"


def test_a_case_sends_the_model_a_trimmed_thread_and_the_ledger_says_so(monkeypatch):
    thread = [turn("old", 3000), turn("mid", 60), turn("new", 60)]
    case, rig = install(monkeypatch, INQUIRY | {"thread": thread})
    rig.replies.append({"output": {"signals": []}})
    asyncio.run(case.safety_screen({}))
    assert agent_context.count_tokens(rig.prompts[0]) <= agent_context.CONTEXT_BUDGET_TOKENS + 200
    assert "new:" in rig.prompts[0] and "old:" not in rig.prompts[0] and INQUIRY["text"] in rig.prompts[0]
    trimmed = [entry for entry in rig.entries if entry["type"] == "context_trimmed"]
    assert trimmed and trimmed[0]["dropped"] == 1 and trimmed[0]["thread_turns"] == 3
    assert len(case.doc["inquiry"]["thread"]) == 3  # the full thread stays in the case


def test_the_plain_rule_screen_reads_the_turns_the_model_never_sees(monkeypatch):
    thread = [{"from": "old", "text": "The patient developed a rash. " + "word " * 3000}, turn("new", 10)]
    case, rig = install(monkeypatch, INQUIRY | {"thread": thread})
    rig.replies.append({"output": {"signals": []}})
    out = asyncio.run(case.safety_screen({}))
    assert out["facts"]["ae"] is True and "rash" not in rig.prompts[0]


def test_every_model_call_records_its_token_estimate(monkeypatch):
    case, rig = install(monkeypatch)
    rig.replies.append({"output": {"signals": []}})
    asyncio.run(case.safety_screen({}))
    call = case.doc["agent_calls"][0]
    assert call["input_tokens_est"] == agent_context.count_tokens(rig.prompts[0])
    assert [e for e in rig.entries if e["type"] == "agent_call"][0]["input_tokens_est"] == call["input_tokens_est"]
