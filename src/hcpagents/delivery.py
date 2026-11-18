"""Real delivery. A reply or an approved touch goes out as an email through SES.

Floci answers SES. Its outbox shows each message at /_aws/ses.
"""

import os

from hcpagents.aws import client


def sender() -> str:
    return os.environ.get("MI_SES_SENDER", "medinfo@quillon.example")


def deliver(to_address: str, subject: str, body: str, tenant: str) -> str:
    """Send one email. Gives back the SES message id. An SES error reaches the caller."""
    ses = client("ses")
    ses.verify_email_identity(EmailAddress=sender())
    sent = ses.send_email(
        Source=sender(),
        Destination={"ToAddresses": [to_address]},
        Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        Tags=[{"Name": "tenant", "Value": tenant}],
    )
    return sent["MessageId"]
