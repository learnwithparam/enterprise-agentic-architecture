"""Sign-in is the identity provider's: the CLI uses the authorization code flow with PKCE, and the API trusts only a
signed token whose tenant claim matches our directory (ADR 0010, ADR 0028)."""

import base64
import hashlib
import inspect
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from hcpagents import api, auth, cli, infra, world
from hcpagents.aws import client
from tests.oauth_helper import hosted_login

pytestmark = pytest.mark.floci


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    infra.provision(reset=True)
    real_get = httpx.get
    monkeypatch.setattr(cli.httpx, "get", lambda url, **kw: TestClient(api.app).get(url.removeprefix(cli.URL)) if url.startswith(cli.URL) else real_get(url, **kw))


def token(user="u-brandt") -> str:
    return cli.sign_in(open_url=lambda url: hosted_login(url, user))


def session(tok: str) -> httpx.Response:
    return TestClient(api.app).get("/api/session", headers={"Authorization": f"Bearer {tok}"})


def test_the_pkce_sign_in_gives_a_token_the_api_accepts():
    r = session(token())
    assert r.status_code == 200 and r.json()["user"]["id"] == "u-brandt"


def test_the_challenge_is_the_sha256_of_the_verifier():
    verifier, challenge = cli.pkce_pair()
    assert challenge == base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert cli.pkce_pair()[0] != verifier


def test_wrong_tenant_token_refused():
    """The token is genuine and unexpired, but its tenant claim differs from the directory's: refused, not scoped to the claim."""
    idp, pool = client("cognito-idp"), auth.pool()
    own = world.person("u-brandt").get("tenant", world.DEFAULT_TENANT)
    other = next(t["id"] for t in world.tenants() if t["id"] != own)
    idp.admin_update_user_attributes(UserPoolId=pool, Username="u-brandt", UserAttributes=[{"Name": "custom:tenant", "Value": other}])
    try:
        r = session(token())
    finally:
        idp.admin_update_user_attributes(UserPoolId=pool, Username="u-brandt", UserAttributes=[{"Name": "custom:tenant", "Value": own}])
    assert r.status_code == 403 and other in r.json()["detail"]


def test_expired_token_refused(monkeypatch):
    tok = token()
    assert session(tok).status_code == 200
    monkeypatch.setattr(auth, "LEEWAY", -2 * 3600)  # the token lives an hour, so it now reads as two hours old
    assert session(tok).status_code == 401


def test_protected_resource_metadata_served():
    c = TestClient(api.app, base_url="http://localhost:8765")
    meta = c.get("/.well-known/oauth-protected-resource")
    assert meta.status_code == 200
    body = meta.json()
    assert body["authorization_servers"] == [auth.issuer()] and body["resource"].endswith("/mcp")
    assert body["bearer_methods_supported"] == ["header"]
    refused = c.get("/v1/cases")
    assert refused.status_code == 401 and "resource_metadata" in refused.headers["www-authenticate"]


def test_password_grant_removed():
    """The CLI has no password option and never calls the password route; its app client allows no password flow."""
    assert list(inspect.signature(cli.login).parameters) == []
    assert not re.search(r"/api/login(?!-)", inspect.getsource(cli)) and '"password"' not in inspect.getsource(cli.sign_in)  # no grant_type or field named password
    c = client("cognito-idp").describe_user_pool_client(UserPoolId=auth.pool(), ClientId=auth.cli_client_id())["UserPoolClient"]
    assert not [f for f in c["ExplicitAuthFlows"] if "PASSWORD" in f]
    assert c["AllowedOAuthFlows"] == ["code"]
    oidc = httpx.get(f"{auth.issuer()}/.well-known/openid-configuration").json()
    refused = httpx.post(oidc["token_endpoint"], data={"grant_type": "password", "client_id": auth.cli_client_id(),
                                                       "username": "u-brandt", "password": auth.DEMO_PASSWORD})
    assert refused.status_code >= 400 and "id_token" not in refused.text
