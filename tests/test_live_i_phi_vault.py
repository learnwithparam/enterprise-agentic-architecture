"""Concept 37: the model sees tokens, the real values sit sealed in a vault of the case, and the reply is restored."""

import json

import pytest

from hcpagents import infra, phi_vault, store, world

TEXT = ("Dr. Elif Kaya (DE-LANR-7731904, +49 30 5550 1904, ekaya@praxis-kaya.example) asks about Veltrona. "
        "Kaya's CRM id is CRM-DE-00412. Please answer Dr. Elif Kaya.")
REAL = ("Kaya", "7731904", "5550 1904", "ekaya@", "00412")


def test_names_ids_phones_and_emails_become_tokens():
    safe = phi_vault.swap_out(TEXT, {})
    for real in REAL:
        assert real not in safe, real
    assert "Veltrona" in safe and "[NAME_1]" in safe and "[PHONE_1]" in safe and "[ID_1]" in safe


def test_the_same_value_gets_the_same_token_and_the_swap_reverses_exactly():
    vault = {}
    safe = phi_vault.swap_out(TEXT, vault)
    assert safe.count("[NAME_1]") == 2
    assert phi_vault.swap_back(safe, vault) == TEXT


def test_a_token_that_is_not_in_the_vault_stays_a_token():
    assert phi_vault.swap_back("Call [PHONE_9]", {"[PHONE_1]": "+49 30 5550 1904"}) == "Call [PHONE_9]"


@pytest.fixture
def fresh():
    infra.provision(reset=True)


@pytest.mark.floci
def test_the_vault_is_sealed_per_case_and_closed_to_other_tenants(fresh):
    safe = phi_vault.tokenise(TEXT, "inq-101")
    stored = json.dumps(store.get(phi_vault.TABLE, "inq-101"))
    for real in REAL:
        assert real not in stored and real not in safe
    assert phi_vault.restore(safe, "inq-101") == TEXT
    assert phi_vault.restore(safe, "inq-102") == safe
    with world.as_tenant("marlowe"):
        assert phi_vault.restore(safe, "inq-101") == safe
