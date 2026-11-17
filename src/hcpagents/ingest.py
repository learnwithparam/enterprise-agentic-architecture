"""Channels tell the platform what happened. They are the CRM, marketing, the call centre and the portal (ADR 0021).

Two doors, one function. A webhook arrives signed with the tenant's secret for that channel.
A nightly batch reads files the channel dropped in S3. Both end in accept, so both are safe to repeat in the same way.
The row id comes from the channel and the sender's own event id.
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
    """The request fails: not from the channel (401), no such channel (404), or not a record (422)."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class Record(BaseModel):
    external_id: str  # the sender id for this event; it makes a repeat safe
    source_id: str  # the sender id for the person: CRM id, phone or portal email
    kind: str
    text: str
    occurred_at: datetime


def secret_for(tenant: str, channel: str) -> str:
    """The signing secret for one tenant's channel. It is kept in SSM so all processes share it, and made on first use."""
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
    """Raise Rejected if the body has no good, fresh signature."""
    if channel not in CHANNELS:
        raise Rejected(f"{channel} is not a channel", 404)
    try:
        seconds = int(timestamp)
    except ValueError as error:
        raise Rejected("Send x-mi-timestamp as whole seconds", 401) from error
    if now is None:
        now = time.time()
    if abs(now - seconds) > TOLERANCE_S:
        raise Rejected("The timestamp is too old or too far ahead", 401)
    if not hmac.compare_digest(sign(secret_for(tenant, channel), seconds, body), signature):
        raise Rejected("The signature does not match", 401)


def accept(tenant: str, channel: str, raw: dict, via: str) -> dict:
    """Store one interaction. Seeing the same event again changes nothing and says so."""
    try:
        record = Record(**raw)
    except ValidationError as error:
        raise Rejected(f"Not a valid record: {error.errors()[0]['loc']}", 422) from error
    row_id = hashlib.sha256(f"{channel}:{record.external_id}".encode()).hexdigest()[:32]
    with world.as_tenant(tenant), db.session() as conn:
        new = conn.execute(
            "INSERT INTO interactions (tenant_id, id, channel, source_id, kind, body, occurred_at, via, hcp_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (tenant, row_id, channel, record.source_id, record.kind, record.text[:4000], record.occurred_at, via,
             identity.resolve(channel, record.source_id))).fetchone()
        if new:
            from hcpagents import events  # events imports infra, which imports this module
            events.publish("InteractionReceived", {"interaction": row_id}, key=f"ix-{row_id}")
    return {"id": row_id, "duplicate": new is None}


def landing() -> None:
    """The bucket where channels drop batch files."""
    s3 = client("s3")
    if BUCKET not in {bucket["Name"] for bucket in s3.list_buckets()["Buckets"]}:
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})


def import_batch(tenant: str) -> dict:
    """Ingest each waiting batch file for a tenant, then move it to done/. A bad line is counted, not fatal."""
    s3, counts = client("s3"), {"new": 0, "duplicate": 0, "rejected": 0, "files": 0}
    for channel in CHANNELS:
        prefix = f"{tenant}/{channel}/incoming/"
        for file in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", []):
            for line in s3.get_object(Bucket=BUCKET, Key=file["Key"])["Body"].read().decode().splitlines():
                try:
                    out = accept(tenant, channel, json.loads(line), via="batch")
                    if out["duplicate"]:
                        counts["duplicate"] += 1
                    else:
                        counts["new"] += 1
                except (Rejected, json.JSONDecodeError):
                    counts["rejected"] += 1
            s3.copy_object(Bucket=BUCKET, CopySource={"Bucket": BUCKET, "Key": file["Key"]},
                           Key=file["Key"].replace("/incoming/", "/done/"))
            s3.delete_object(Bucket=BUCKET, Key=file["Key"])
            counts["files"] += 1
    return counts
