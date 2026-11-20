"""Swap personal data for tokens before a model reads it. Swap it back after (concept 37).

Names, ids, emails and phone numbers become tokens such as [NAME_1]. The model only sees the tokens.
The real values wait in a vault. Each case has one vault. It sits in the rows of its tenant and is sealed with a key.
Another tenant cannot open it. Delete the key and the vault is gone.
The vault never goes into a prompt, a trace or a reply.
"""

import base64
import json
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from hcpagents import pii_detector, privacy, store, world

TABLE = "mi-phi"
NONCE_BYTES = 12
TITLED_NAME = re.compile(r"\b(?:Dr|Prof|Mr|Mrs|Ms)\.? [A-Z][a-z]+(?: [A-Z][a-z]+)?")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
IDENTIFIER = re.compile(r"\b(?:[A-Z]{2,}-)+\d{4,}\b|\b(?:MRN|mk)[- ]?\d{4,}\b")
PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
TOKEN = re.compile(r"\[(?:NAME|EMAIL|ID|PHONE|DOB|ADDRESS)_\d+\]")
TITLES = {"dr", "dr.", "prof", "mr", "mrs", "ms"}


def _known_names() -> list[str]:
    """Every doctor name of this tenant, whole and in parts. The longest come first."""
    found = set()
    for doctor in world.hcp_world()["hcp"]:
        found.add(doctor["name"])
        for part in doctor["name"].split():
            if part.lower() not in TITLES and len(part) > 3:
                found.add(part)
    return sorted(found, key=len, reverse=True)


def _token_for(vault: dict, kind: str, original: str) -> str:
    """The token of a value. The same value in the same case always gets the same token."""
    for token, value in vault.items():
        if value == original:
            return token
    count = sum(1 for token in vault if token.startswith(f"[{kind}_")) + 1
    token = f"[{kind}_{count}]"
    vault[token] = original
    return token


def _swap_pattern(text: str, vault: dict, kind: str, pattern: re.Pattern) -> str:
    def swap(match: re.Match) -> str:
        return _token_for(vault, kind, match.group(0))

    return pattern.sub(swap, text)


def swap_out(text: str, vault: dict) -> str:
    """The text with each personal value replaced by its token. New values are added to the vault."""
    text = _swap_pattern(text, vault, "EMAIL", EMAIL)
    text = _swap_pattern(text, vault, "ID", IDENTIFIER)
    text = _swap_pattern(text, vault, "PHONE", PHONE)
    for name in _known_names():
        text = _swap_pattern(text, vault, "NAME", re.compile(rf"\b{re.escape(name)}\b"))
    text = _swap_pattern(text, vault, "NAME", TITLED_NAME)
    return _swap_found(text, vault)


def _swap_found(text: str, vault: dict) -> str:
    """Swap what the detector finds in free text. It runs last, and values that are already tokens are left alone."""
    for start, end, kind in reversed(pii_detector.find(text)):
        value = text[start:end]
        if not TOKEN.fullmatch(value):
            text = text[:start] + _token_for(vault, kind, value) + text[end:]
    return text


def swap_back(text: str, vault: dict) -> str:
    """The text with each token of this vault replaced by its real value. Other tokens stay as they are."""
    def swap(match: re.Match) -> str:
        return vault.get(match.group(0), match.group(0))

    return TOKEN.sub(swap, text)


def _key(case_id: str) -> AESGCM:
    return AESGCM(privacy.tenant_key("key", f"phi-{case_id}"))


def _open(case_id: str) -> dict:
    """The vault of a case. It is empty when there is none, or when it cannot be opened with this tenant's key."""
    doc = store.get(TABLE, case_id)
    if doc is None:
        return {}
    raw = base64.b64decode(doc["sealed"])
    try:
        return json.loads(_key(case_id).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], case_id.encode()))
    except InvalidTag:
        return {}


def _close(case_id: str, vault: dict) -> None:
    nonce = os.urandom(NONCE_BYTES)
    cipher = _key(case_id).encrypt(nonce, json.dumps(vault).encode(), case_id.encode())
    store.put(TABLE, {"id": case_id, "sealed": base64.b64encode(nonce + cipher).decode()})


def tokenise(text: str, case_id: str) -> str:
    """The text for the model. Personal values are tokens, and the real values are sealed in the case vault."""
    # Step 1: Open the vault of this case.
    vault = _open(case_id)
    before = dict(vault)
    # Step 2: Swap each personal value for one token.
    safe = swap_out(text, vault)
    # Step 3: Seal the vault again if it grew.
    if vault != before:
        _close(case_id, vault)
    return safe


def restore(text: str, case_id: str) -> str:
    """The text for the reader. Each token of this case is turned back into the real value."""
    return swap_back(text, _open(case_id))
