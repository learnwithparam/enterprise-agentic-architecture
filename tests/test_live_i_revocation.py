"""Concept 39: a revoked user stops working on the next call, and a cache outage never lets one back in."""

import pytest
from fastapi.testclient import TestClient

from hcpagents import api, auth, cache, infra, revocation, world
from tests.test_flow import as_user

TENANT = world.DEFAULT_TENANT


class Offline:
    """A cache that cannot be reached."""

    def exists(self, name):
        raise cache.DOWN[1]("down")


def test_a_cache_outage_refuses_the_call_instead_of_skipping_the_check(monkeypatch):
    monkeypatch.setattr(cache, "_client", Offline)
    with pytest.raises(revocation.Revoked):
        revocation.check(TENANT, "u-raman")


@pytest.mark.floci
def test_a_revoked_user_is_refused_on_the_next_call_on_every_machine_route():
    infra.provision(reset=True)
    http = TestClient(api.app, base_url="http://localhost:8765")
    header = as_user("u-raman")
    assert http.get("/v1/cases", headers=header).status_code == 200
    auth.revoke_user(TENANT, "u-raman")
    try:
        for path in ("/v1/cases", "/v1/releases", "/api/session"):
            refused = http.get(path, headers=header)
            assert refused.status_code == 401 and "revoked" in refused.json()["detail"], path
        assert http.get("/v1/cases", headers=as_user("u-brandt")).status_code == 200
    finally:
        auth.reinstate_user(TENANT, "u-raman")
    assert http.get("/v1/cases", headers=header).status_code == 200
