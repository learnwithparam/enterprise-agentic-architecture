"""The content firewall. Who is asking decides which blocks can be found, before any ranking."""

import pytest

from hcpagents import guards, infra, retrieval, world

DOCTOR_ONLY = {"VEL-US-RENAL", "VEL-US-PREG", "VEL-US-INTER"}


@pytest.fixture(scope="module")
def fresh():
    infra.provision(reset=True)


def found(query, audience, product="VEL", country="US"):
    return [block["block_id"] for block in retrieval.search(query, product, country, limit=30, audience=audience)]


@pytest.mark.floci
def test_a_rep_never_gets_a_doctor_only_answer(fresh):
    for query in ("kidney disease dose", "pregnancy", "drug interactions", "dose"):
        assert not DOCTOR_ONLY & set(found(query, "rep"))
    assert DOCTOR_ONLY & set(found("kidney disease dose", "doctor"))


@pytest.mark.floci
def test_the_chatbot_gets_only_its_own_script_word_for_word(fresh):
    answer = retrieval.search("where is the prescribing information", "VEL", "US", limit=30, audience="chatbot")
    assert [block["block_id"] for block in answer] == ["SS-VEL-US-FIND"]
    script = next(block for block in world.blocks() if block["id"] == "SS-VEL-US-FIND")
    assert answer[0]["text"] == script["text"]


@pytest.mark.floci
def test_a_doctor_never_gets_the_chatbot_script(fresh):
    assert "SS-VEL-US-FIND" not in found("prescribing information website", "doctor")


@pytest.mark.floci
def test_the_chatbot_script_stays_in_its_own_country(fresh):
    assert found("prescribing information", "chatbot", country="DE") == ["SS-VEL-DE-FIND"]


def test_every_block_names_a_type_and_who_may_see_it():
    kinds = {"PI": {"doctor", "rep"}, "SRD": {"doctor"}, "SELF_SERVICE": {"chatbot"}, "TEMPLATE": {"doctor", "rep", "chatbot"}}
    for block in world.blocks():
        assert set(block["audience"]) == kinds[block["doc_type"]], block["id"]


def test_the_check_after_a_tool_runs_drops_a_block_the_asker_may_not_see():
    srd = next(block for block in world.blocks() if block["id"] == "VEL-US-RENAL")
    rep_case = {"country": "US", "product": "VEL", "channel": "crm"}
    doctor_case = {"country": "US", "product": "VEL", "channel": "portal"}
    assert not guards._fits_case(srd, rep_case)
    assert guards._fits_case(srd, doctor_case)


def test_a_block_with_no_audience_is_shown_to_nobody():
    assert not guards._fits_case({"country": "US", "product": "VEL"}, {"country": "US", "product": "VEL"})


def test_the_asker_comes_from_the_channel():
    assert world.audience_of({"channel": "crm"}) == "rep"
    assert world.audience_of({"inquiry": {"channel": "chatbot"}}) == "chatbot"
    assert world.audience_of({"inquiry": {"channel": "portal"}}) == "doctor"
