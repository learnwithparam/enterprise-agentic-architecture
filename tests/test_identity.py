"""A channel's own id resolves to one doctor of one tenant, or to nobody (ADR 0022)."""

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, hcp360, identity, infra, ingest, world

pytestmark = pytest.mark.floci

KAYA = {"crm": "CRM-DE-00412", "marketing": "mk-88213", "contact_centre": "+49 30 5550 1904",
        "portal": "ekaya@praxis-kaya.example"}


def test_every_channel_handle_resolves_to_the_doctor_it_belongs_to():
    with world.as_tenant("quillon"):
        assert {ch: identity.resolve(ch, v) for ch, v in KAYA.items()} == dict.fromkeys(KAYA, "hcp-kaya")


def test_formatting_does_not_split_one_doctor_in_two():
    with world.as_tenant("quillon"):
        assert identity.resolve("contact_centre", "0049-30-5550-1904") is None  # a different number
        assert identity.resolve("contact_centre", "+49 (30) 5550 1904") == "hcp-kaya"
        assert identity.resolve("portal", "  EKaya@Praxis-Kaya.example ") == "hcp-kaya"


def test_the_registry_id_works_on_any_channel():
    with world.as_tenant("quillon"):
        assert identity.resolve("crm", "DE-LANR-7731904") == "hcp-kaya"


def test_a_handle_of_another_tenant_or_nobody_stays_unresolved():
    with world.as_tenant("quillon"):
        assert identity.resolve("crm", "CRM-M-0001") is None
        assert identity.resolve("crm", "CRM-NOBODY") is None
    with world.as_tenant("marlowe"):
        assert identity.resolve("crm", "CRM-M-0001") == "hcp-m-ortiz"
        assert identity.resolve("crm", KAYA["crm"]) is None


def test_a_handle_shared_by_two_doctors_is_never_guessed(monkeypatch):
    two = {"hcp": [{"id": "a", "registry_id": "R1", "records": {"crm": "X"}},
                   {"id": "b", "registry_id": "R2", "records": {"crm": "x"}}]}
    monkeypatch.setattr(world, "hcp_world", lambda: two)
    assert identity.resolve("crm", "X") is None
    assert identity.resolve("crm", "R2") == "b"


def _send(c, channel, source_id, tenant="quillon"):
    body = json.dumps({"external_id": uuid.uuid4().hex, "source_id": source_id, "kind": "visit_note",
                       "text": "Asked about dosing.", "occurred_at": "2026-10-28T09:30:00Z"}).encode()
    ts = int(time.time())
    sig = ingest.sign(ingest.secret_for(tenant, channel), ts, body)
    r = c.post(f"/hooks/{tenant}/{channel}", content=body, headers={"x-mi-timestamp": str(ts), "x-mi-signature": sig})
    assert r.status_code == 202
    return r.json()["id"]


def test_a_landed_interaction_joins_the_360_of_its_doctor_and_unknowns_wait_for_a_human():
    infra.provision(reset=True)
    c, stranger = TestClient(api.app), "stranger-" + uuid.uuid4().hex
    known, unknown = _send(c, "portal", KAYA["portal"]), _send(c, "crm", stranger)
    with world.as_tenant("quillon"):
        assert known in {i["id"] for i in hcp360.view("hcp-kaya")["interactions"]}
        waiting = {r["id"] for r in identity.unresolved()}
        assert unknown in waiting and known not in waiting
        assert unknown not in {i["id"] for i in hcp360.view("hcp-kaya")["interactions"]}


def test_a_handle_that_becomes_known_later_links_what_already_arrived(monkeypatch):
    infra.provision(reset=True)
    late = "late-" + uuid.uuid4().hex
    row = _send(TestClient(api.app), "crm", late)
    grown = {"hcp": [dict(h, records=dict(h["records"], crm=late)) if h["id"] == "hcp-kaya" else h
                     for h in world.hcp_world()["hcp"]]}
    with world.as_tenant("quillon"):
        assert row in {r["id"] for r in identity.unresolved()}
        monkeypatch.setattr(world, "hcp_world", lambda: grown)
        assert identity.link_pending() >= 1
        assert row in {i["id"] for i in identity.interactions("hcp-kaya")}
        assert row not in {r["id"] for r in identity.unresolved()}


def test_one_tenant_never_reads_the_interactions_of_another():
    infra.provision(reset=True)
    row = _send(TestClient(api.app), "portal", KAYA["portal"])
    with world.as_tenant("marlowe"):
        assert row not in {i["id"] for i in identity.interactions("hcp-kaya")}
        assert row not in {r["id"] for r in identity.unresolved()}
