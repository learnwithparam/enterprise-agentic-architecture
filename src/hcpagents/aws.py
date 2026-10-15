"""boto3 clients pointed at Floci, the local AWS emulator. In production the same code runs
against real AWS by unsetting MI_AWS_ENDPOINT; nothing else changes."""

import os
from functools import cache

import boto3

ENDPOINT = os.environ.get("MI_AWS_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_REGION", "eu-central-1")


@cache
def client(service: str):
    kw = {"region_name": REGION}
    if ENDPOINT:
        # Floci accepts any credentials; these are not secrets.
        kw |= {"endpoint_url": ENDPOINT, "aws_access_key_id": "test", "aws_secret_access_key": "test"}
    return boto3.client(service, **kw)


def floci_up() -> bool:
    try:
        client("dynamodb").list_tables(Limit=1)
        return True
    except Exception:
        return False
