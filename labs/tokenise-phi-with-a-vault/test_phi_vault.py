"""Tokenise personal data with a vault. The model sees tokens, and the reader gets the real values back."""

from hcpagents import phi_vault

QUESTION = ("Dr. Elif Kaya (DE-LANR-7731904, +49 30 5550 1904) asks how Veltrona is stored. "
            "Please write back to Dr. Elif Kaya.")
REAL = ("Kaya", "7731904", "5550 1904")


def test_step_1_the_model_sees_tokens_and_no_personal_value():
    # Step 1
    safe = phi_vault.swap_out(QUESTION, {})
    for real in REAL:
        assert real not in safe
    assert "Veltrona" in safe


def test_step_2_the_same_person_is_the_same_token_so_the_model_can_follow_who_is_who():
    # Step 2
    safe = phi_vault.swap_out(QUESTION, {})
    assert safe.count("[NAME_1]") == 2


def test_step_3_the_reply_is_restored_from_the_vault_of_the_case():
    # Step 3
    vault = {}
    safe = phi_vault.swap_out(QUESTION, vault)
    assert phi_vault.swap_back("Dear [NAME_1], store it cool.", vault) == "Dear Dr. Elif Kaya, store it cool."
    assert phi_vault.swap_back(safe, vault) == QUESTION


def test_step_4_a_token_from_another_case_stays_a_token():
    # Step 4
    other_case = {"[NAME_1]": "Someone Else"}
    assert phi_vault.swap_back("Call [PHONE_1]", other_case) == "Call [PHONE_1]"


def test_step_5_a_patient_name_a_birth_date_and_an_address_are_tokens_too():
    # Step 5
    text = "Patient Maria Lopez, born 4 March 1961, lives at 12 Elm Street. Veltrona dose in renal impairment?"
    safe = phi_vault.swap_out(text, {})
    for real in ("Lopez", "1961", "Elm Street"):
        assert real not in safe
    assert "Veltrona" in safe and "renal impairment" in safe
