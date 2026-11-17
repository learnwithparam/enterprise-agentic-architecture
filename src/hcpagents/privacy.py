"""Each person's data in the ledger is sealed with their own key. To erase them, delete the key.

The ledger only grows, and it is locked for ten years. So a name or a quoted symptom cannot be deleted from it.
It does not have to be. The ledger holds a pseudonym and ciphertext. The key sits in SSM, one for each person.

Deleting the key leaves each hash, signature and archived object as it was. The text can no longer be read (ADR 0015).
The pseudonym is an HMAC under a secret for each tenant. It links one person's entries to each other and to nothing else.
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
    except ClientError as error:
        if error.response["Error"]["Code"] == "ParameterNotFound":
            return None
        raise


def _put(name: str, value: bytes) -> None:
    client("ssm").put_parameter(Name=name, Value=base64.b64encode(value).decode(), Type="SecureString", Overwrite=True)


def _secret(kind: str, ident: str) -> bytes:
    """Read a 32-byte secret. Make it the first time it is used."""
    name = _name(kind, ident)
    found = _get(name)
    if found:
        return found
    _put(name, os.urandom(32))
    return _get(name)


def pseudonym(subject: str) -> str:
    pepper = _secret("pepper", "tenant")
    return hmac.new(pepper, subject.encode(), hashlib.sha256).hexdigest()[:20]


def seal(subject: str, data: dict) -> dict:
    """The two ledger fields that replace the personal data. They are who it is about (a pseudonym) and the ciphertext."""
    pid = pseudonym(subject)
    nonce = os.urandom(NONCE_BYTES)
    cipher = AESGCM(_secret("key", pid)).encrypt(nonce, json.dumps(data, ensure_ascii=False).encode(), pid.encode())
    return {"subject": pid, "sealed": base64.b64encode(nonce + cipher).decode()}


def reveal(entry: dict) -> dict:
    """The entry with its sealed data opened as private. Once the key is gone, private is erased."""
    if "sealed" not in entry:
        return entry
    plain = {name: value for name, value in entry.items() if name != "sealed"}
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
    """Delete the key of the person. True if there was a key to delete."""
    name = _name("key", pseudonym(subject))
    if _get(name) is None:
        return False
    client("ssm").delete_parameter(Name=name)
    return True
