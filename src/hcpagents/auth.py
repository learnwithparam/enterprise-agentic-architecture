"""Who is calling, proved by a signed token.

The identity provider (Cognito, or any OIDC issuer) signs an ID token. We verify the signature against
its published keys, then the issuer, the audience, the expiry and the token type. The tenant never comes
from the caller: it comes from our own directory, so a token cannot name its way into another client.
"""

import os
from datetime import UTC, datetime
from functools import cache

import jwt

from hcpagents import db, world
from hcpagents.aws import ENDPOINT, REGION, client

DEMO_PASSWORD = os.environ.get("MI_DEMO_PASSWORD", "local-demo-only")  # synthetic users on the local emulator


CLI_REDIRECT = os.environ.get("HCP_REDIRECT", "http://127.0.0.1:8976/callback")  # where the hcp CLI listens for the sign-in code
LEEWAY = 0  # seconds of clock slack on expiry; tests make it negative to meet a real token after its expiry


class Unauthenticated(Exception):
    pass


class WrongTenant(Exception):
    """The token is genuine but names a different tenant than our directory does."""


@cache
def pool() -> str:
    return client("ssm").get_parameter(Name="/mi/cognito/pool")["Parameter"]["Value"]


@cache
def client_id() -> str:
    return client("ssm").get_parameter(Name="/mi/cognito/client")["Parameter"]["Value"]


@cache
def cli_client_id() -> str:
    return client("ssm").get_parameter(Name="/mi/cognito/cli-client")["Parameter"]["Value"]


def issuer() -> str:
    base = ENDPOINT or f"https://cognito-idp.{REGION}.amazonaws.com"
    return f"{base}/{pool()}"


@cache
def _keys() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{issuer()}/.well-known/jwks.json", cache_keys=True)


def login(user_id: str, password: str) -> str:
    """Exchange a password for an ID token. Only the sign-in route calls this."""
    try:
        r = client("cognito-idp").admin_initiate_auth(
            UserPoolId=pool(), ClientId=client_id(), AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": user_id, "PASSWORD": password})
    except Exception as e:
        raise Unauthenticated("Wrong user or password") from e
    return r["AuthenticationResult"]["IdToken"]


def verify(token: str) -> dict:
    """The signed-in user, or Unauthenticated. Checks signature, issuer, audience, expiry and token type."""
    try:
        key = _keys().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer(), audience=[client_id(), cli_client_id()],
                            leeway=LEEWAY, options={"require": ["exp", "iss", "aud", "sub"]})
    except Exception as e:
        raise Unauthenticated("Sign in again") from e
    if claims.get("token_use") != "id":
        raise Unauthenticated("Not an ID token")
    uid = claims["cognito:username"]
    person = world.person(uid)
    if person is None:
        raise Unauthenticated("Unknown user")
    tenant = person.get("tenant", db.DEFAULT_TENANT)
    if claims.get("custom:tenant") != tenant:
        raise WrongTenant(f"The token names tenant {claims.get('custom:tenant')!r}, not {tenant!r}")
    return {"id": uid, "name": claims["name"], "role": claims["custom:role"], "country": claims["custom:country"],
            "title": person["title"], "tenant": tenant}


def reauthenticate(user: dict, password: str) -> dict:
    """The approver signs in again at the moment of approving. The result is their electronic signature (ADR 0017)."""
    try:
        signed_in = verify(login(user["id"], password))
    except Unauthenticated as e:
        raise Unauthenticated("Signing needs your password again") from e
    if signed_in["id"] != user["id"]:
        raise Unauthenticated("Signing needs your own password")
    return {"user": user["id"], "name": user["name"], "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "meaning": "approved the reply", "method": "password"}
