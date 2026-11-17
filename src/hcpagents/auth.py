"""Who is calling, proved by a signed token.

The identity provider signs an ID token. It can be Cognito or any OIDC issuer.
We check the signature against its public keys. Then we check the issuer, the audience, the expiry and the token type.
The tenant never comes from the caller. It comes from our own directory, so a token cannot name its way into another client.
"""

import os
from datetime import UTC, datetime
from functools import cache

import jwt

from hcpagents import db, world
from hcpagents.aws import ENDPOINT, REGION, client

DEMO_PASSWORD = os.environ.get("MI_DEMO_PASSWORD", "local-demo-only")  # fake users on the local emulator


CLI_REDIRECT = os.environ.get("HCP_REDIRECT", "http://127.0.0.1:8976/callback")  # where the hcp CLI waits for the sign-in code
LEEWAY = 0  # seconds of slack for the clock. Tests make it negative to test a late token.


class Unauthenticated(Exception):
    pass


class WrongTenant(Exception):
    """The token is real, but its tenant is not the one we have on file."""


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
    """Swap a password for an ID token. Only the sign-in route calls this."""
    try:
        result = client("cognito-idp").admin_initiate_auth(
            UserPoolId=pool(), ClientId=client_id(), AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": user_id, "PASSWORD": password})
    except Exception as error:
        raise Unauthenticated("Wrong user or password") from error
    return result["AuthenticationResult"]["IdToken"]


def verify(token: str) -> dict:
    """Return the signed-in user, or raise Unauthenticated. The token must be signed, fresh and meant for us."""
    try:
        key = _keys().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer(), audience=[client_id(), cli_client_id()],
                            leeway=LEEWAY, options={"require": ["exp", "iss", "aud", "sub"]})
    except Exception as error:
        raise Unauthenticated("Sign in again") from error
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
    """The approver signs in again when they approve. That sign-in is their electronic signature (ADR 0017)."""
    try:
        signed_in = verify(login(user["id"], password))
    except Unauthenticated as error:
        raise Unauthenticated("Signing needs your password again") from error
    if signed_in["id"] != user["id"]:
        raise Unauthenticated("Signing needs your own password")
    return {"user": user["id"], "name": user["name"], "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "meaning": "approved the reply", "method": "password"}
