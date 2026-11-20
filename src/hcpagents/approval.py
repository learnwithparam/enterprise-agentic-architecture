"""What a reviewer's signature is bound to.

A signature on "approve" alone could be reused for another reply. So the signature covers a digest of the exact
reply: its text, each block and version, the doctor, the country, the release and the draft version. The digest is
signed with the ledger key. At send time the digest is worked out again. If any part moved, nothing goes out.
"""

import hashlib
import json

from hcpagents import ledger


def digest(text: str, segments: list[dict], hcp_id: str | None, country: str, release_id: str | None,
           draft_version: int | None) -> str:
    blocks = sorted([segment["block_id"], segment["version"]] for segment in segments)
    body = {"text": text, "blocks": blocks, "hcp": hcp_id, "country": country, "release": release_id,
            "draft_version": draft_version}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _of_draft(doc: dict, release_id: str | None, draft_version: int | None) -> str:
    hcp = None
    if doc.get("hcp"):
        hcp = doc["hcp"]["id"]
    return digest(doc["draft"]["text"], doc["draft"]["segments"], hcp, doc["country"], release_id, draft_version)


def _message(user_id: str, signed_at: str, value: str) -> str:
    return f"{user_id}|{signed_at}|{value}"


def bind(doc: dict, signature: dict) -> dict:
    """The record of one approval. It keeps the release and draft version as they were when the person signed."""
    release_id, draft_version = doc.get("release"), doc.get("draft_version")
    value = _of_draft(doc, release_id, draft_version)
    return {"user": signature["user"], "meaning": signature["meaning"], "method": signature["method"],
            "signed_at": signature["at"], "release": release_id, "draft_version": draft_version, "digest": value,
            "kms_signature": ledger.seal(_message(signature["user"], signature["at"], value))}


def problems(doc: dict) -> list[str]:
    """Why the signature no longer covers this draft. An empty list means it still does."""
    record = doc.get("approval")
    if not record:
        return ["no approval is bound to this draft"]
    found = []
    value = _of_draft(doc, record["release"], record["draft_version"])
    if value != record["digest"]:
        found.append("the reply changed after it was signed")
    if doc.get("draft_version") != record["draft_version"]:
        found.append("the draft was written again after it was signed")
    message = _message(record["user"], record["signed_at"], record["digest"])
    if not ledger.seal_ok(message, record["kms_signature"]):
        found.append("the signature does not match the key")
    return found
