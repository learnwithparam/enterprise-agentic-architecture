"""The user pool settings used in the cloud and on a laptop.

Both read this file, so they match.
"""

import os

# Each custom attribute, and whether it may change later.
ATTRIBUTES = {"tenant": False, "role": True, "country": True}

POOL_PARAMETER = "/mi/cognito/pool"
CLIENT_PARAMETER = "/mi/cognito/client"
CLI_CLIENT_PARAMETER = "/mi/cognito/cli-client"
USER_SECRET_PREFIX = "/mi/users/"  # one local password per demo user

PASSWORD_MIN_LENGTH = 14
PASSWORD_REQUIRES = {"digits": True, "symbols": True, "lowercase": True, "uppercase": True}

CLI_REDIRECT = os.environ.get("HCP_REDIRECT", "http://127.0.0.1:8976/callback")  # where the CLI waits for the code
