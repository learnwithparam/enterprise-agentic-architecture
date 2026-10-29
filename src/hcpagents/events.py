"""Handoffs between the platform and the humans who own each outcome travel as EventBridge events
on the mi-events bus, delivered to one SQS queue per owning team.

Delivery is at least once, so every event carries an id and a consumer handles each id once (ADR 0020).
An event that fails every attempt is parked in dead_letters with its error, and can be replayed."""

import json
import uuid
from collections.abc import Callable

from hcpagents import db, world
from hcpagents.aws import client
from hcpagents.infra import BUS, QUEUES

MAX_ATTEMPTS = 3


def publish(detail_type: str, detail: dict, key: str | None = None) -> str:
    """Send an event. The same `key` published twice is one event to every consumer."""
    event_id = key or uuid.uuid4().hex
    detail = {"tenant": world.current_tenant(), **detail, "event_id": event_id}
    client("events").put_events(Entries=[{
        "Source": "mi.platform", "DetailType": detail_type, "EventBusName": BUS,
        "Detail": json.dumps(detail, ensure_ascii=False),
    }])
    return event_id


def _url(queue: str) -> str:
    return client("sqs").get_queue_url(QueueName=queue)["QueueUrl"]


def depth() -> dict[str, int]:
    sqs = client("sqs")
    return {q: int(sqs.get_queue_attributes(QueueUrl=_url(q), AttributeNames=["ApproximateNumberOfMessages"])
                   ["Attributes"]["ApproximateNumberOfMessages"]) for q in QUEUES}


def _seen(tenant: str, event_id: str, queue: str) -> bool:
    with world.as_tenant(tenant), db.session() as conn:
        return conn.execute("SELECT 1 FROM processed_events WHERE event_id = %s AND queue = %s", (event_id, queue)).fetchone() is not None


def _mark(tenant: str, event_id: str, queue: str) -> None:
    with world.as_tenant(tenant), db.session() as conn:
        conn.execute("INSERT INTO processed_events (tenant_id, event_id, queue) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (tenant, event_id, queue))


def _park(tenant: str, queue: str, detail: dict, error: str, attempts: int) -> None:
    with world.as_tenant(tenant), db.session() as conn:
        conn.execute("INSERT INTO dead_letters (tenant_id, queue, event_id, detail, error, attempts) VALUES (%s, %s, %s, %s, %s, %s)",
                     (tenant, queue, detail["event_id"], json.dumps(detail), error[:500], attempts))


def consume(queue: str, handler: Callable[[dict], None]) -> int:
    """Hand every waiting event to `handler` once, inside the tenant it names. Returns how many were handled.
    A failure leaves the message for another try; after MAX_ATTEMPTS it goes to dead_letters."""
    sqs, url, handled = client("sqs"), _url(queue), 0
    while True:
        msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=0, AttributeNames=["ApproximateReceiveCount"]).get("Messages", [])
        if not msgs:
            return handled
        for m in msgs:
            body = json.loads(m["Body"])
            detail = body.get("detail", body)
            tenant, event_id = detail["tenant"], detail["event_id"]
            if not _seen(tenant, event_id, queue):
                try:
                    with world.as_tenant(tenant):
                        handler(detail)
                except Exception as e:  # noqa: BLE001 - any handler failure is retried, then parked
                    attempts = int(m["Attributes"]["ApproximateReceiveCount"])
                    if attempts < MAX_ATTEMPTS:
                        sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"], VisibilityTimeout=0)
                        continue
                    _park(tenant, queue, detail, f"{type(e).__name__}: {e}", attempts)
                else:
                    _mark(tenant, event_id, queue)
                    handled += 1
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])


def dead_letters() -> list[dict]:
    """The current tenant's parked events that have not been replayed."""
    with db.session() as conn:
        return conn.execute("SELECT id, queue, event_id, error, attempts, created_at FROM dead_letters "
                            "WHERE replayed_at IS NULL ORDER BY id").fetchall()


def replay(dead_letter_id: int) -> str:
    """Put a parked event back on the bus under its own id, so its handler runs again."""
    with db.session() as conn:
        row = conn.execute("UPDATE dead_letters SET replayed_at = now() WHERE id = %s AND replayed_at IS NULL "
                           "RETURNING queue, detail", (dead_letter_id,)).fetchone()
    if row is None:
        raise LookupError(f"No parked event {dead_letter_id} waiting for replay")
    detail_type = QUEUES[row["queue"]]
    return publish(detail_type, row["detail"], key=row["detail"]["event_id"])
