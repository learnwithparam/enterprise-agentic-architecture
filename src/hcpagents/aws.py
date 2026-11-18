"""boto3 clients for AWS.

Production reads no endpoint and talks to real AWS. A local run sets MI_AWS_ENDPOINT to Floci, the local AWS copy.
MI_ENV is "local" only on a laptop. Anything else is production.
"""

import os
from functools import cache

import boto3

ENDPOINT = os.environ.get("MI_AWS_ENDPOINT", "")
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


def is_local() -> bool:
    """True only when the run says so. Demo routes and password sign-in exist only then."""
    return os.environ.get("MI_ENV", "production") == "local"
