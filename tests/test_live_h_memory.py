"""A handoff needs a reason and both parties. Shared memory is checked before anyone reads it."""

from datetime import date

import pytest

from hcpagents import handoff_workers, memory, store

NOTE = {"id": "n-1", "hcp": "hcp-kaya", "text": "Prefers email", "source": "crm:CRM-DE-00412", "expires_on": "2026-12-01",
        "author": "outreach-coordinator"}
TODAY = date(2026, 10, 15)


@pytest.mark.parametrize("field", ["source", "expires_on", "author", "hcp", "id"])
def test_a_note_without_a_required_field_is_refused(field):
    with pytest.raises(memory.Refused, match=field):
        memory.remember({key: value for key, value in NOTE.items() if key != field}, TODAY)


def test_an_expired_note_and_another_tenants_note_are_refused():
    with pytest.raises(memory.Refused, match="expired"):
        memory.remember(NOTE | {"expires_on": "2026-10-14"}, TODAY)
    with pytest.raises(memory.Refused, match="another tenant"):
        memory.remember(NOTE | {"tenant": "other"}, TODAY)


def test_a_note_that_went_stale_or_crossed_a_tenant_is_never_read(monkeypatch):
    stored = [NOTE | {"tenant": "quillon"}, NOTE | {"id": "n-2", "expires_on": "2026-10-01", "tenant": "quillon"},
              NOTE | {"id": "n-3", "tenant": "other"}, NOTE | {"id": "n-4", "source": "", "tenant": "quillon"}]
    monkeypatch.setattr(store, "scan", lambda table: stored)
    assert [note["id"] for note in memory.recall("hcp-kaya", TODAY)] == ["n-1"]


@pytest.mark.parametrize("field", ["sender", "receiver", "case_id", "reason"])
def test_a_handoff_without_a_reason_or_a_party_is_refused(field):
    args = {"sender": "inquiry-agent", "receiver": "pharmacovigilance", "case_id": "inq-9", "reason": "Rash reported"}
    args[field] = ""
    with pytest.raises(ValueError, match="needs a"):
        handoff_workers.hand_off(**args)
