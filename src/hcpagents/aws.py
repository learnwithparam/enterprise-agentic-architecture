"""boto3 clients that talk to Floci, the local AWS copy.

In production the same code talks to real AWS. Unset MI_AWS_ENDPOINT and nothing else changes.
"""

import os
from functools import cache

import boto3

ENDPOINT = os.environ.get("MI_AWS_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_REGION", "eu-central-1")


@cache
def client(service: str):
    options = {"region_name": REGION}
    if ENDPOINT:
        # Floci accepts any keys, so these are not secrets.
        options |= {"endpoint_url": ENDPOINT, "aws_access_key_id": "test", "aws_secret_access_key": "test"}
    return boto3.client(service, **options)


def floci_up() -> bool:
    try:
        client("dynamodb").list_tables(Limit=1)
        return True
    except Exception:
        return False
