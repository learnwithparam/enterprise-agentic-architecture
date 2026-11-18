"""Compliance can stop a user and let them back in, from the API and the CLI (live lab 39)."""

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, auth, cli, infra, world
from tests.test_flow import as_user

pytestmark = pytest.mark.floci


def test_compliance_revokes_a_user_and_the_next_call_with_their_token_is_refused_until_they_are_reinstated():
    infra.provision(reset=True)
    web = TestClient(api.app)
    reviewer = as_user("u-brandt")
    assert web.get("/v1/cases", headers=reviewer).status_code == 200
    assert web.post("/v1/users/u-raman/revoke", headers=reviewer).status_code == 403
    compliance = as_user("u-raman")
    assert web.post("/v1/users/u-brandt/revoke", headers=compliance).json()["status"] == "access_revoked"
    assert web.get("/v1/cases", headers=reviewer).status_code == 401
    assert web.post("/v1/users/u-brandt/reinstate", headers=compliance).json()["status"] == "access_reinstated"
    assert web.get("/v1/cases", headers=reviewer).status_code == 200


def test_an_unknown_user_is_404_and_nobody_may_revoke_themselves():
    infra.provision(reset=True)
    web = TestClient(api.app)
    compliance = as_user("u-raman")
    assert web.post("/v1/users/u-nobody/revoke", headers=compliance).status_code == 404
    assert web.post("/v1/users/u-raman/revoke", headers=compliance).status_code == 409


def test_the_cli_has_a_command_for_each_route():
    names = {command.name or command.callback.__name__ for command in cli.app.registered_commands}
    assert {"revoke", "reinstate"} <= names


def test_a_reset_puts_a_revoked_demo_user_back_so_a_half_run_test_cannot_lock_out_the_next():
    infra.provision(reset=True)
    auth.revoke_user(world.DEFAULT_TENANT, "u-raman")
    infra.provision(reset=True)
    assert as_user("u-raman")["Authorization"].startswith("Bearer ")
    assert TestClient(api.app).get("/v1/cases", headers=as_user("u-raman")).status_code == 200
