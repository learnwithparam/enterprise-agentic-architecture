"""The data firewall (blueprint, "data firewall"). The commercial role cannot reach medical or safety data, and the
only thing that crosses is a hold with no case id. These tests try to break that against the real database."""

import ast
import json
from pathlib import Path

import psycopg
import pytest

from hcpagents import db, infra, store, views

SRC = Path(__file__).parent.parent / "src" / "hcpagents"
pytestmark = pytest.mark.floci

CASE = {"id": "inq-zone-1", "hcp": {"id": "hcp-kaya"}, "product": "VEL", "status": "awaiting_review", "country": "DE",
        "route": "review", "text": "the patient had a rash"}


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def commercial():
    return db.zone_session(views.COMMERCIAL)


def test_the_commercial_role_cannot_read_or_write_the_medical_and_safety_zones():
    for zone in ("medical", "safety"):
        with commercial() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"SELECT 1 FROM {zone}.docs")
        with commercial() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"INSERT INTO {zone}.docs (tenant_id, kind, id, doc) VALUES ('x', 'cases', 'x', '{{}}')")


def test_the_commercial_role_sees_only_content_in_the_shared_table():
    store.put("mi-users", {"id": "u-zone", "role": "pv"})
    with commercial() as conn:
        kinds = {row["kind"] for row in conn.execute("SELECT kind FROM public.docs")}
    assert kinds == {"content"}


def test_nobody_writes_a_hold_directly():
    for role_session in (db.session, commercial):
        with role_session() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO shared.contact_hold VALUES ('x', 'hcp-kaya', 'VEL', 'open_medical_case')")


def test_an_open_case_holds_promotion_and_the_commercial_view_never_names_it():
    store.put("mi-cases", CASE)
    view = views.commercial_view("hcp-kaya")
    held = [p for p in view["planned"] if "open_medical_case" in p["decision"]["rules"]]
    assert held
    text = json.dumps(view) + json.dumps(views.commercial_summary())
    assert "inq-zone-1" not in text and "rash" not in text and "open_cases" not in text


def test_a_finished_touch_that_came_from_a_case_shows_no_case_id_to_commercial():
    store.put("mi-touches", {"id": "t-zone", "hcp": "hcp-kaya", "status": "done", "on": "2026-11-01", "channel": "email",
                             "kind": "email", "case": "inq-zone-9", "summary": "Answered a question"})
    assert "inq-zone-9" not in json.dumps(views.commercial_view("hcp-kaya"))


def test_commercial_touches_show_only_allowed_fields_and_no_case_id_in_the_summary():
    store.put("mi-touches", {"id": "t-zone2", "hcp": "hcp-kaya", "status": "done", "on": "2026-11-02", "channel": "email",
                             "kind": "mi_reply", "case": "inq-zone-8", "source": "inq-zone-8", "reasons": ["inq-zone-8"],
                             "summary": "Medical information reply sent for case inq-zone-8."})
    view = views.commercial_view("hcp-kaya")
    assert "inq-zone-8" not in json.dumps(view)
    assert all(set(touch) <= set(views.SHOWN) for touch in view["timeline"])


def test_closing_the_case_lifts_the_hold_and_a_second_open_case_keeps_it():
    store.put("mi-cases", CASE)
    store.put("mi-cases", CASE | {"id": "inq-zone-2"})
    store.put("mi-cases", CASE | {"status": "sent"})
    with commercial() as conn:
        assert conn.execute("SELECT count(*) AS n FROM shared.contact_hold").fetchone()["n"] == 1
    store.put("mi-cases", CASE | {"id": "inq-zone-2", "status": "sent"})
    with commercial() as conn:
        assert conn.execute("SELECT count(*) AS n FROM shared.contact_hold").fetchone()["n"] == 0


def test_a_safety_freeze_holds_every_product_and_names_no_case():
    store.put("mi-freezes", {"id": "freeze-i1", "hcp": "hcp-kaya", "case": "pv-secret", "interaction": "i1"})
    view = views.commercial_view("hcp-kaya")
    assert all("safety_freeze" in p["decision"]["rules"] for p in view["planned"]) and view["planned"]
    assert "pv-secret" not in json.dumps(view)


def test_cedar_gives_reviewers_the_medical_view_and_reps_the_commercial_one():
    store.put("mi-cases", CASE)
    person = {"id": "u1", "name": "Pat", "country": "DE"}
    rep = views.view_for(person | {"role": "field_rep"}, "hcp-kaya")
    reviewer = views.view_for(person | {"role": "medical_reviewer"}, "hcp-kaya")
    assert rep["zone"] == "commercial" and "open_cases" not in rep
    assert reviewer["zone"] == "medical" and [c["id"] for c in reviewer["open_cases"]] == ["inq-zone-1"]


def test_agent_modules_import_no_database_layer():
    """The model side of the system never reaches a table. Only service modules do."""
    banned = {"psycopg", "db", "store"}
    for name in ("agents.py", "agents_options.py", "agents_spec.py", "agents_tools.py", "graph.py", "kernel.py",
                 "plan.py", "rules.py", "grounding.py", "guards.py"):
        tree = ast.parse((SRC / name).read_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                found |= {alias.name for alias in node.names} if node.module == "hcpagents" else {(node.module or "").split(".")[0]}
        assert not found & banned, f"{name} imports {sorted(found & banned)}"
