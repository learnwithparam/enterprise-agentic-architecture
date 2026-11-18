"""Production and the local emulator agree on identity, and a sign-in challenge is an error, not a crash. No service needed."""

import re
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template
from stack import Platform

from hcpagents import auth, identity_spec

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def template():
    app = cdk.App()
    return Template.from_stack(Platform(app, "T", env=cdk.Environment(account="123456789012", region="eu-central-1")))


def test_the_pool_has_every_attribute_the_app_reads_and_requires_mfa(template):
    (pool,) = template.find_resources("AWS::Cognito::UserPool").values()
    schema = {entry["Name"]: entry["Mutable"] for entry in pool["Properties"]["Schema"]}
    assert schema == identity_spec.ATTRIBUTES
    assert pool["Properties"]["MfaConfiguration"] == "ON"
    policy = pool["Properties"]["Policies"]["PasswordPolicy"]
    assert policy["MinimumLength"] == identity_spec.PASSWORD_MIN_LENGTH


def test_the_stack_writes_the_ssm_names_the_app_reads(template):
    names = {r["Properties"]["Name"] for r in template.find_resources("AWS::SSM::Parameter").values()}
    assert names == {identity_spec.POOL_PARAMETER, identity_spec.CLIENT_PARAMETER, identity_spec.CLI_CLIENT_PARAMETER}


def test_the_cli_client_uses_the_code_flow_and_the_callback_the_cli_waits_on(template):
    clients = template.find_resources("AWS::Cognito::UserPoolClient").values()
    (cli,) = [c["Properties"] for c in clients if c["Properties"].get("AllowedOAuthFlows")]
    assert cli["AllowedOAuthFlows"] == ["code"] and cli["CallbackURLs"] == [auth.CLI_REDIRECT]
    assert "ExplicitAuthFlows" not in cli or not [f for f in cli["ExplicitAuthFlows"] if "PASSWORD" in f]


def test_only_the_shared_spec_names_the_identity_parameters():
    """A second spelling of a parameter name is a second source of truth."""
    offenders = [str(path.relative_to(ROOT)) for folder in ("src", "deploy") for path in (ROOT / folder).rglob("*.py")
                 if path.name != "identity_spec.py" and re.search(r"/mi/(cognito|users)", path.read_text())]
    assert not offenders, offenders


class StubIdp:
    """Cognito answering a sign-in with a challenge, then a token when the code is right."""

    def __init__(self, challenge: str):
        self.challenge = challenge
        self.calls = []

    def admin_initiate_auth(self, **kwargs):
        self.calls.append("initiate")
        return {"ChallengeName": self.challenge, "Session": "s1"}

    def admin_respond_to_auth_challenge(self, **kwargs):
        self.calls.append("respond")
        assert kwargs["ChallengeResponses"]["SOFTWARE_TOKEN_MFA_CODE"] == "123456"
        return {"AuthenticationResult": {"IdToken": "signed"}}


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setenv("MI_ENV", "local")
    monkeypatch.setattr(auth, "pool", lambda: "pool")
    monkeypatch.setattr(auth, "client_id", lambda: "client")

    def use(challenge: str) -> StubIdp:
        idp = StubIdp(challenge)
        monkeypatch.setattr(auth, "client", lambda service: idp)
        return idp

    return use


def test_an_mfa_challenge_is_unauthenticated_not_a_key_error(stub):
    stub("SOFTWARE_TOKEN_MFA")
    with pytest.raises(auth.Unauthenticated, match="MFA code needed"):
        auth.login("u-brandt", "pw")


def test_an_mfa_code_answers_the_challenge(stub):
    idp = stub("SOFTWARE_TOKEN_MFA")
    assert auth.login("u-brandt", "pw", mfa_code="123456") == "signed"
    assert idp.calls == ["initiate", "respond"]


def test_a_new_password_challenge_is_unauthenticated(stub):
    stub("NEW_PASSWORD_REQUIRED")
    with pytest.raises(auth.Unauthenticated, match="NEW_PASSWORD_REQUIRED"):
        auth.login("u-brandt", "pw", mfa_code="123456")


def test_password_sign_in_refuses_outside_the_local_emulator(stub, monkeypatch):
    idp = stub("SOFTWARE_TOKEN_MFA")
    monkeypatch.setenv("MI_ENV", "production")
    with pytest.raises(auth.Unauthenticated, match="local emulator"):
        auth.login("u-brandt", "pw")
    assert idp.calls == []


@pytest.mark.floci
def test_each_local_user_has_their_own_random_password():
    from hcpagents import infra
    from hcpagents.aws import client
    for user_id in ("u-brandt", "u-hale"):  # remove the old secrets so provision has to make new ones
        client("secretsmanager").delete_secret(SecretId=identity_spec.USER_SECRET_PREFIX + user_id, ForceDeleteWithoutRecovery=True)
    infra.provision()
    first, second = auth.local_password("u-brandt"), auth.local_password("u-hale")
    assert first != second and "local-demo-only" not in (first, second)
    assert len(first) >= identity_spec.PASSWORD_MIN_LENGTH
    assert auth.verify(auth.login("u-brandt", first))["id"] == "u-brandt"
