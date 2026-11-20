"""Split data into zones. Commercial cannot reach medical data. A hold names no case."""

import json

import psycopg
import pytest

from hcpagents import db, infra, store, views

pytestmark = pytest.mark.floci

CASE = {"id": "inq-lab-1", "hcp": {"id": "hcp-kaya"}, "product": "VEL", "status": "awaiting_review", "country": "DE",
        "route": "review", "text": "the patient had a rash"}


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def test_the_commercial_login_is_refused_on_medical_and_safety():
    for zone in ("medical", "safety"):
        with db.zone_session(views.COMMERCIAL) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"SELECT 1 FROM {zone}.docs")


def test_an_open_case_holds_promotion_and_the_commercial_view_never_names_it():
    store.put("mi-cases", CASE)
    view = views.commercial_view("hcp-kaya")
    assert [plan for plan in view["planned"] if "open_medical_case" in plan["decision"]["rules"]]
    assert "inq-lab-1" not in json.dumps(view) and "rash" not in json.dumps(view)


def test_closing_the_case_lifts_the_hold_and_no_login_writes_one_directly():
    store.put("mi-cases", CASE)
    store.put("mi-cases", CASE | {"status": "sent"})
    with db.zone_session(views.COMMERCIAL) as conn:
        assert conn.execute("SELECT count(*) AS n FROM shared.contact_hold").fetchone()["n"] == 0
    with db.session() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO shared.contact_hold VALUES ('x', 'hcp-kaya', 'VEL', 'open_medical_case')")


def test_a_field_rep_gets_the_commercial_view_and_a_reviewer_the_medical_one():
    store.put("mi-cases", CASE)
    person = {"id": "u1", "name": "Pat", "country": "DE"}
    assert views.view_for(person | {"role": "field_rep"}, "hcp-kaya")["zone"] == "commercial"
    assert views.view_for(person | {"role": "medical_reviewer"}, "hcp-kaya")["zone"] == "medical"
