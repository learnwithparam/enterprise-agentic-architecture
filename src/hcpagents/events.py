"""Handoffs between the platform and the humans who own each outcome travel as EventBridge events
on the mi-events bus, delivered to one SQS queue per owning team."""

import json

from hcpagents.aws import client
from hcpagents.infra import BUS, QUEUES


def publish(detail_type: str, detail: dict) -> None:
    client("events").put_events(Entries=[{
        "Source": "mi.platform", "DetailType": detail_type, "EventBusName": BUS,
        "Detail": json.dumps(detail, ensure_ascii=False),
    }])


def _url(queue: str) -> str:
    return client("sqs").get_queue_url(QueueName=queue)["QueueUrl"]


def depth() -> dict[str, int]:
    sqs = client("sqs")
    return {q: int(sqs.get_queue_attributes(QueueUrl=_url(q), AttributeNames=["ApproximateNumberOfMessages"])
                   ["Attributes"]["ApproximateNumberOfMessages"]) for q in QUEUES}


def drain(queue: str) -> list[dict]:
    """Receive and delete everything waiting on a queue. Returns the event details."""
    sqs, url, out = client("sqs"), _url(queue), []
    while True:
        msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=0).get("Messages", [])
        if not msgs:
            return out
        for m in msgs:
            body = json.loads(m["Body"])
            out.append(body.get("detail", body))
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
