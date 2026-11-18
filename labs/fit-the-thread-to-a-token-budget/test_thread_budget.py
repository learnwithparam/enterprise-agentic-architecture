"""Fit the thread to a token budget. The oldest turns go first. The question and the newest turn always stay."""

import pytest

from hcpagents import agent_context, agents


def turn(who: str, words: int) -> dict:
    return {"from": who, "text": " ".join(["word"] * words)}


def test_a_thread_over_the_budget_loses_its_oldest_turns_first():
    thread = [turn("a", 40), turn("b", 40), turn("c", 40), turn("d", 40)]
    fitted = agent_context.fit_thread(thread, "Where is it stored?", budget=130)
    assert [kept["from"] for kept in fitted["kept"]] == ["c", "d"]
    assert fitted["dropped"] == 2 and fitted["tokens"] <= 130


def test_the_question_and_the_newest_turn_stay_even_when_nothing_else_fits():
    fitted = agent_context.fit_thread([turn("a", 40), turn("b", 40)], "Where is it stored?", budget=75)
    assert [kept["from"] for kept in fitted["kept"]] == ["b"]


def test_a_thread_that_fits_is_kept_whole():
    assert agent_context.fit_thread([turn("a", 5), turn("b", 5)], "Q?")["dropped"] == 0


def test_an_inquiry_with_no_thread_reaches_the_model_word_for_word():
    text, note = agent_context.model_text({"text": "Where is it stored?"})
    assert text == "Where is it stored?" and note["dropped"] == 0


def test_a_question_too_big_for_the_budget_goes_to_a_person_and_is_never_cut():
    big_question = " ".join(["word"] * 400)
    with pytest.raises(agents.EscalateToHuman):
        agent_context.fit_thread([turn("a", 5)], big_question, budget=100)
