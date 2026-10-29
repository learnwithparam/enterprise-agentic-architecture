"""Personal data in the ledger is sealed under a key per person, and erasing the person deletes the key.

The ledger is append-only and locked for ten years, so a name or a quoted symptom cannot be deleted from it.
It does not have to be. The ledger stores a pseudonym and ciphertext; the key sits in SSM, one per person.
Deleting the key leaves every hash, signature and archived object untouched and makes the text unreadable
(ADR 0015). The pseudonym is an HMAC under a per-tenant secret, so it links one person's entries to each
other and to nothing else.
"""

import base64
import hashlib
import hmac
import json
import os

from botocore.exceptions import ClientError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from hcpagents import world
from hcpagents.aws import client

NONCE_BYTES = 12


def _name(kind: str, ident: str) -> str:
    return f"/mi/privacy/{world.current_tenant()}/{kind}/{ident}"


def _get(name: str) -> bytes | None:
    try:
        return base64.b64decode(client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ParameterNotFound":
            return None
        raise


def _put(name: str, value: bytes) -> None:
    client("ssm").put_parameter(Name=name, Value=base64.b64encode(value).decode(), Type="SecureString", Overwrite=True)


def _secret(kind: str, ident: str) -> bytes:
    """Read a 32-byte secret, creating it on first use."""
    name = _name(kind, ident)
    return _get(name) or (_put(name, os.urandom(32)), _get(name))[1]


def pseudonym(subject: str) -> str:
    pepper = _secret("pepper", "tenant")
    return hmac.new(pepper, subject.encode(), hashlib.sha256).hexdigest()[:20]


def seal(subject: str, data: dict) -> dict:
    """The two ledger fields that replace the personal data: who it is about (pseudonym) and the ciphertext."""
    pid = pseudonym(subject)
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(_secret("key", pid)).encrypt(nonce, json.dumps(data, ensure_ascii=False).encode(), pid.encode())
    return {"subject": pid, "sealed": base64.b64encode(nonce + ct).decode()}


def reveal(entry: dict) -> dict:
    """The entry with its sealed data opened as `private`, or `private: {"erased": True}` once the key is gone."""
    if "sealed" not in entry:
        return entry
    plain = {k: v for k, v in entry.items() if k != "sealed"}
    key = _get(_name("key", entry["subject"]))
    if key is None:
        return plain | {"private": {"erased": True}}
    raw = base64.b64decode(entry["sealed"])
    try:
        data = AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], entry["subject"].encode())
    except InvalidTag:
        return plain | {"private": {"unreadable": True}}
    return plain | {"private": json.loads(data)}


def erase(subject: str) -> bool:
    """Delete the person's key. True when there was a key to delete."""
    name = _name("key", pseudonym(subject))
    if _get(name) is None:
        return False
    client("ssm").delete_parameter(Name=name)
    return True
