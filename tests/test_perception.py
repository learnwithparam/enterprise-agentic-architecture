"""The sentinel reads every channel without being asked, and the insight agent only reports what several doctors share (ADR 0024)."""

import json
from datetime import UTC, datetime
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, events, infra, ingest, insight, ledger, outreach, sentinel, world

pytestmark = pytest.mark.floci

ID = {"kaya_portal": "ekaya@praxis-kaya.example", "brenner_crm": "CRM-DE-00977"}


def send(c, channel, source_id, text, tenant="quillon"):
    body = json.dumps({"external_id": uuid.uuid4().hex, "source_id": source_id, "kind": "visit_note", "text": text,
                       "occurred_at": "2026-10-28T09:30:00Z"}).encode()
    ts = int(time.time())
    sig = ingest.sign(ingest.secret_for(tenant, channel), ts, body)
    r = c.post(f"/hooks/{tenant}/{channel}", content=body, headers={"x-mi-timestamp": str(ts), "x-mi-signature": sig})
    assert r.status_code == 202
    return r.json()["id"]


def pv_cases() -> list[dict]:
    got: list[dict] = []
    events.consume("mi-pv-intake", got.append)
    return got


def test_a_rash_in_a_rep_note_opens_a_safety_case_and_freezes_contact_with_nobody_asking():
    infra.provision(reset=True)
    c = TestClient(api.app)
    note = send(c, "crm", ID["brenner_crm"], "Patient on Veltrona developed a rash after two weeks.")
    send(c, "portal", ID["kaya_portal"], "Thanks, the dosing card was helpful.")
    assert sentinel.perceive() == 2
    with world.as_tenant("quillon"):
        signals = pv_cases()
        assert [(s["case"], s["interaction"], s["hcp"]) for s in signals] == [(f"pv-{note}", note, "hcp-brenner")]
        plan = {d["id"]: d for d in outreach.coordinate("hcp-brenner")}
        assert plan["plan-brenner-visit"]["action"] == "hold"
        freeze = next(r for r in plan["plan-brenner-visit"]["reasons"] if r["rule"] == "safety_freeze")
        assert freeze["source"] == note
        assert all(r["rule"] != "safety_freeze" for d in outreach.coordinate("hcp-kaya") for r in d["reasons"])
        assert any(r["entry"]["type"] == "sentinel_signal" and r["entry"]["interaction"] == note for r in ledger.entries())


def test_an_unlinked_sender_still_raises_the_signal_but_freezes_nobody():
    infra.provision(reset=True)
    note = send(TestClient(api.app), "contact_centre", "+00 000 unknown", "Caller reports a seizure in a patient.")
    assert sentinel.perceive() == 1
    with world.as_tenant("quillon"):
        assert [s["interaction"] for s in pv_cases()] == [note]
        assert all(r["rule"] != "safety_freeze" for h in ("hcp-kaya", "hcp-brenner") for d in outreach.coordinate(h) for r in d["reasons"])


def test_the_same_event_read_twice_raises_one_signal():
    infra.provision(reset=True)
    c = TestClient(api.app)
    send(c, "crm", ID["brenner_crm"], "Swelling reported by a patient.")
    assert sentinel.perceive() == 1
    assert sentinel.perceive() == 0
    with world.as_tenant("quillon"):
        assert len(pv_cases()) == 1


def test_a_theme_needs_two_doctors_and_names_its_sources_but_never_quotes_them():
    infra.provision(reset=True)
    c, start = TestClient(api.app), datetime.now(UTC)
    one = send(c, "crm", ID["brenner_crm"], "Asked about renal dosing again, SECRET-WORDING-1")
    assert not [t for t in _themes(start) if t["topic"] == "renal_impairment"]
    two = send(c, "portal", ID["kaya_portal"], "Question on kidney function and dose, SECRET-WORDING-2")
    theme = next(t for t in _themes(start) if t["topic"] == "renal_impairment")
    assert theme["hcps"] == 2 and theme["channels"] == ["crm", "portal"] and {one, two} <= set(theme["sources"])
    assert "SECRET-WORDING" not in json.dumps(theme)


def _themes(start: datetime) -> list[dict]:
    with world.as_tenant("quillon"):
        return insight.digest(start)
