"""JSON documents in DynamoDB tables keyed by id. Content, cases, HCPs and touches all use this."""

import json

from hcpagents.aws import client


def get(table: str, doc_id: str) -> dict | None:
    it = client("dynamodb").get_item(TableName=table, Key={"id": {"S": doc_id}}, ConsistentRead=True).get("Item")
    return json.loads(it["doc"]["S"]) if it else None


def put(table: str, doc: dict) -> None:
    client("dynamodb").put_item(TableName=table, Item={"id": {"S": doc["id"]}, "doc": {"S": json.dumps(doc, ensure_ascii=False)}})


def scan(table: str) -> list[dict]:
    out = []
    for page in client("dynamodb").get_paginator("scan").paginate(TableName=table, ConsistentRead=True):
        out += [json.loads(it["doc"]["S"]) for it in page["Items"]]
    return out


def content() -> dict[str, dict]:
    """The content store as it is now, keyed by block id."""
    return {b["id"]: b for b in scan("mi-content")}
