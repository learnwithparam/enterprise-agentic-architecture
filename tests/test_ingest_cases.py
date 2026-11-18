"""A signed question from any channel opens one medical information case, and a repeat opens none."""

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from hcpagents import agents, api, cases, infra, ingest, store, world

pytestmark = pytest.mark.floci

QUESTION = "What is the recommended starting dose of Veltrona, and can my patients take it with food?"
KAYA = {"crm": "CRM-DE-00412", "marketing": "mk-88213", "contact_centre": "+49 30 5550 1904",
        "portal": "ekaya@praxis-kaya.example"}


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def post(channel: str, rec: dict):
    body = json.dumps(rec).encode()
    ts = int(time.time())
    sig = ingest.sign(ingest.secret_for("quillon", channel), ts, body)
    headers = {"x-mi-timestamp": str(ts), "x-mi-signature": sig}
    return TestClient(api.app).post(f"/hooks/quillon/{channel}", content=body, headers=headers)


def record(source_id: str, **over) -> dict:
    return {"external_id": uuid.uuid4().hex, "source_id": source_id, "kind": "question", "text": QUESTION,
            "occurred_at": "2026-10-28T09:30:00Z"} | over


def case_ids() -> set[str]:
    with world.as_tenant("quillon"):
        return {doc["id"] for doc in store.scan("mi-cases") if doc["id"].startswith("ix-")}


@pytest.mark.parametrize("channel", ingest.CHANNELS)
def test_a_signed_question_opens_exactly_one_case_and_a_repeat_opens_none(channel, monkeypatch):
    before, rec = case_ids(), record(KAYA[channel])
    row_id = post(channel, rec).json()["id"]
    assert case_ids() - before == {f"ix-{row_id}"}
    with world.as_tenant("quillon"):
        assert store.get("mi-cases", f"ix-{row_id}")["hcp"]["id"] == "hcp-kaya"
    runs = []
    real_run = cases.run
    monkeypatch.setattr(cases, "run", lambda *args: runs.append(args) or real_run(*args))
    assert post(channel, rec).json()["duplicate"] is True
    assert runs == []  # the repeat must not run the case again
    assert case_ids() - before == {f"ix-{row_id}"}


def test_a_question_from_an_unknown_sender_opens_a_case_that_is_not_sent():
    before = case_ids()
    row_id = post("portal", record("nobody@example.test")).json()["id"]
    assert case_ids() - before == {f"ix-{row_id}"}
    with world.as_tenant("quillon"):
        doc = store.get("mi-cases", f"ix-{row_id}")
    assert doc["hcp"] is None and doc["route"] in ("review", "specialist")


def test_other_kinds_open_no_case():
    before = case_ids()
    post("crm", record(KAYA["crm"], kind="visit_note"))
    assert case_ids() == before


def test_a_question_whose_case_cannot_open_is_kept_logged_and_opened_on_a_repeat(monkeypatch):
    from hcpagents import ledger

    async def no_recording(*args):
        raise agents.MissingRecording("No recording for this text")

    monkeypatch.setattr(cases, "run", no_recording)
    before, rec = case_ids(), record(KAYA["crm"], text="A question nobody recorded an answer for.")
    first = post("crm", rec)
    assert first.status_code == 202
    row_id = first.json()["id"]
    assert first.json() == {"id": row_id, "duplicate": False, "case": "pending"}
    assert case_ids() == before
    with world.as_tenant("quillon"):
        failures = [r["entry"] for r in ledger.entries() if r["entry"].get("type") == "case_open_failed" and r["entry"].get("row") == row_id]
    assert failures and failures[0]["error"] == "MissingRecording"

    runs = []

    async def succeed(case_id, inquiry):
        runs.append(case_id)
        with world.as_tenant("quillon"):
            store.put("mi-cases", {"id": case_id})

    monkeypatch.setattr(cases, "run", succeed)
    again = post("crm", rec).json()
    assert again["duplicate"] is True and "case" not in again
    assert post("crm", rec).json()["duplicate"] is True
    assert runs == [f"ix-{row_id}"]
    assert case_ids() - before == {f"ix-{row_id}"}
