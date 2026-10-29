"""Channel ingestion: the CRM, marketing, contact centre and portal tell the platform what happened (ADR 0021).

Two doors, one function. A webhook arrives signed with the tenant's secret for that channel; a nightly
batch reads files the channel dropped in S3. Both end in `accept`, so both are idempotent the same way:
the row id comes from the channel and the sender's own event id.
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime

from pydantic import BaseModel, ValidationError

from hcpagents import db, identity, world
from hcpagents.aws import REGION, client

CHANNELS = ("crm", "marketing", "contact_centre", "portal")
BUCKET = "mi-ingest"
TOLERANCE_S = 300  # a signed request older than this is a replay


class Rejected(Exception):
    """The request is not from the channel it names (401), names no channel (404) or is not a record (422)."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class Record(BaseModel):
    external_id: str  # the sender's id for this event; the idempotency key
    source_id: str  # the sender's id for the person (CRM id, phone, portal email)
    kind: str
    text: str
    occurred_at: datetime


def secret_for(tenant: str, channel: str) -> str:
    """The signing secret for one tenant's channel. Kept in SSM so every process shares it; made on first use."""
    name = f"/mi/ingest/{tenant}/{channel}"
    ssm = client("ssm")
    try:
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        value = secrets.token_urlsafe(32)
        ssm.put_parameter(Name=name, Value=value, Type="SecureString")
        return value


def sign(secret: str, timestamp: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify(tenant: str, channel: str, timestamp: str, signature: str, body: bytes, now: float | None = None) -> None:
    """Raise Rejected unless this body was signed with the channel's secret within the last few minutes."""
    if channel not in CHANNELS:
        raise Rejected(f"{channel} is not a channel", 404)
    try:
        ts = int(timestamp)
    except ValueError as e:
        raise Rejected("Send x-mi-timestamp as whole seconds", 401) from e
    if abs((now if now is not None else time.time()) - ts) > TOLERANCE_S:
        raise Rejected("The timestamp is too old or too far ahead", 401)
    if not hmac.compare_digest(sign(secret_for(tenant, channel), ts, body), signature):
        raise Rejected("The signature does not match", 401)


def accept(tenant: str, channel: str, raw: dict, via: str) -> dict:
    """Store one interaction. Seeing the same event again changes nothing and says so."""
    try:
        r = Record(**raw)
    except ValidationError as e:
        raise Rejected(f"Not a valid record: {e.errors()[0]['loc']}", 422) from e
    row_id = hashlib.sha256(f"{channel}:{r.external_id}".encode()).hexdigest()[:32]
    with world.as_tenant(tenant), db.session() as conn:
        new = conn.execute(
            "INSERT INTO interactions (tenant_id, id, channel, source_id, kind, body, occurred_at, via, hcp_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (tenant, row_id, channel, r.source_id, r.kind, r.text[:4000], r.occurred_at, via,
             identity.resolve(channel, r.source_id))).fetchone()
        if new:
            from hcpagents import events  # events imports infra, which imports this module
            events.publish("InteractionReceived", {"interaction": row_id}, key=f"ix-{row_id}")
    return {"id": row_id, "duplicate": new is None}


def landing() -> None:
    """The bucket where channels drop batch files: <tenant>/<channel>/incoming/*.jsonl."""
    s3 = client("s3")
    if BUCKET not in {b["Name"] for b in s3.list_buckets()["Buckets"]}:
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})


def import_batch(tenant: str) -> dict:
    """Ingest every waiting batch file for a tenant, then move each to done/. A bad line is counted, not fatal."""
    s3, counts = client("s3"), {"new": 0, "duplicate": 0, "rejected": 0, "files": 0}
    for channel in CHANNELS:
        prefix = f"{tenant}/{channel}/incoming/"
        for obj in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", []):
            for line in s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read().decode().splitlines():
                try:
                    out = accept(tenant, channel, json.loads(line), via="batch")
                    counts["duplicate" if out["duplicate"] else "new"] += 1
                except (Rejected, json.JSONDecodeError):
                    counts["rejected"] += 1
            s3.copy_object(Bucket=BUCKET, CopySource={"Bucket": BUCKET, "Key": obj["Key"]}, Key=obj["Key"].replace("/incoming/", "/done/"))
            s3.delete_object(Bucket=BUCKET, Key=obj["Key"])
            counts["files"] += 1
    return counts
