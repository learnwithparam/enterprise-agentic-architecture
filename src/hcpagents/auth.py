"""Who is calling, proved by a signed token.

The identity provider signs an ID token. It can be Cognito or any OIDC issuer.
We check the signature against its public keys. Then we check the issuer, the audience, the expiry and the token type.
The tenant never comes from the caller. It comes from our own directory, so a token cannot name its way into another client.
"""

import sys
import time
from datetime import UTC, datetime
from functools import cache

import jwt
from botocore.exceptions import ClientError

from hcpagents import db, identity_spec, revocation, world
from hcpagents.aws import ENDPOINT, REGION, client, is_local

CLI_REDIRECT = identity_spec.CLI_REDIRECT  # where the hcp CLI waits for the sign-in code
LEEWAY = 10  # Seconds a token may be issued in the future. The provider's clock can run ahead. Expiry gets no slack.
# Tests make it negative to test a late token.


class Unauthenticated(Exception):
    pass


class WrongTenant(Exception):
    """The token is real, but its tenant is not the one we have on file."""


@cache
def pool() -> str:
    return client("ssm").get_parameter(Name=identity_spec.POOL_PARAMETER)["Parameter"]["Value"]


@cache
def client_id() -> str:
    return client("ssm").get_parameter(Name=identity_spec.CLIENT_PARAMETER)["Parameter"]["Value"]


@cache
def cli_client_id() -> str:
    return client("ssm").get_parameter(Name=identity_spec.CLI_CLIENT_PARAMETER)["Parameter"]["Value"]


def issuer() -> str:
    base = ENDPOINT or f"https://cognito-idp.{REGION}.amazonaws.com"
    return f"{base}/{pool()}"


@cache
def _keys() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{issuer()}/.well-known/jwks.json", cache_keys=True)


def local_password(user_id: str) -> str:
    """The random password made for one local demo user. It is kept in the secret store."""
    return client("secretsmanager").get_secret_value(SecretId=identity_spec.USER_SECRET_PREFIX + user_id)["SecretString"]


def _answer_challenge(idp, user_id: str, result: dict, mfa_code: str | None) -> dict:
    """Cognito asked for one more step. We can answer an authenticator code and nothing else."""
    name = result.get("ChallengeName", "")
    if name != "SOFTWARE_TOKEN_MFA":
        raise Unauthenticated(f"Sign-in needs a step this API cannot do: {name or 'unknown'}")
    if not mfa_code:
        raise Unauthenticated("MFA code needed")
    return idp.admin_respond_to_auth_challenge(
        UserPoolId=pool(), ClientId=client_id(), ChallengeName=name, Session=result["Session"],
        ChallengeResponses={"USERNAME": user_id, "SOFTWARE_TOKEN_MFA_CODE": mfa_code})


def login(user_id: str, password: str, mfa_code: str | None = None) -> str:
    """Swap a password for an ID token. Only the sign-in route calls this, and only on the local emulator."""
    if not is_local():
        raise Unauthenticated("Password sign-in is for the local emulator. Sign in through the identity page")
    idp = client("cognito-idp")
    try:
        result = idp.admin_initiate_auth(
            UserPoolId=pool(), ClientId=client_id(), AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": user_id, "PASSWORD": password})
    except Exception as error:
        raise Unauthenticated("Wrong user or password") from error
    if "AuthenticationResult" not in result:
        try:
            result = _answer_challenge(idp, user_id, result, mfa_code)
        except Unauthenticated:
            raise
        except Exception as error:
            raise Unauthenticated("Wrong MFA code") from error
    return result["AuthenticationResult"]["IdToken"]


def decode(token: str, key, issuer: str, audience: list[str]) -> dict:
    """Check the signature, issuer, audience and expiry. Expiry gets no slack, so a token ends when it says.
    Only the issued-at time gets slack. A clock that runs ahead makes a fresh token look new."""
    claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer, audience=audience,
                        options={"require": ["exp", "iss", "aud", "sub"], "verify_aud": True, "verify_iat": False})
    if claims.get("iat", 0) > time.time() + LEEWAY:
        raise jwt.ImmatureSignatureError("The token is issued too far in the future")
    return claims


def verify(token: str) -> dict:
    """Return the signed-in user, or raise Unauthenticated. The token must be signed, fresh and meant for us."""
    try:
        key = _keys().get_signing_key_from_jwt(token).key
        claims = decode(token, key, issuer(), [client_id(), cli_client_id()])
    except Exception as error:
        print(f"token refused: {type(error).__name__}: {error}", file=sys.stderr)  # The caller only sees "Sign in again".
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
    try:
        revocation.check(tenant, uid)
    except revocation.Revoked as error:
        print(f"user refused: {error} ({error.__cause__!r})", file=sys.stderr)
        raise Unauthenticated(str(error)) from error
    return {"id": uid, "name": claims["name"], "role": claims["custom:role"], "country": claims["custom:country"],
            "title": person["title"], "tenant": tenant}


def _tell_identity_provider(action: str, user_id: str) -> None:
    """Turn the user off or on at the identity provider. A local emulator may not know these calls."""
    try:
        getattr(client("cognito-idp"), action)(UserPoolId=pool(), Username=user_id)
    except ClientError:
        if not is_local():
            raise


def revoke_user(tenant: str, user_id: str) -> None:
    """Stop this user now. Their tokens are refused on the next call, and they cannot sign in again."""
    revocation.add(tenant, user_id)
    _tell_identity_provider("admin_disable_user", user_id)
    _tell_identity_provider("admin_user_global_sign_out", user_id)


def reinstate_user(tenant: str, user_id: str) -> None:
    """Let a revoked user back in."""
    revocation.remove(tenant, user_id)
    _tell_identity_provider("admin_enable_user", user_id)


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


if __name__ == "__main__":
    print(local_password(sys.argv[1]))  # uv run python -m hcpagents.auth u-raman
