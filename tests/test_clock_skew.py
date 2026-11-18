"""A token signed by a clock a few seconds ahead of ours must still be accepted. One minute ahead must not.

Found on 18 Nov 2026: three of thirty runs of one test got 401 with "token is not yet valid (iat)", because the leeway was 0.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from hcpagents import auth

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signed_at(seconds_from_now: int) -> str:
    issued = int(time.time()) + seconds_from_now
    claims = {"iss": "i", "aud": "a", "sub": "s", "iat": issued, "exp": issued + 3600}
    return jwt.encode(claims, KEY, algorithm="RS256")


def decode(token: str) -> dict:
    return jwt.decode(token, KEY.public_key(), algorithms=["RS256"], issuer="i", audience=["a"], leeway=auth.LEEWAY)


def test_a_token_from_a_clock_a_few_seconds_ahead_is_accepted():
    assert decode(signed_at(3))["sub"] == "s"


def test_a_token_from_a_clock_a_minute_ahead_is_refused():
    with pytest.raises(jwt.ImmatureSignatureError):
        decode(signed_at(60))
