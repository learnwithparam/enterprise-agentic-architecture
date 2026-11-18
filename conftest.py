import os

# Tests run against Floci on a laptop. Production sets none of these. The limits are high so many sign-ins in one run pass.
os.environ.setdefault("MI_ENV", "local")
os.environ.setdefault("MI_AWS_ENDPOINT", "http://localhost:4566")
os.environ.setdefault("MI_LOGIN_PER_MIN", "100000")
os.environ.setdefault("MI_HOOK_PER_MIN", "100000")

import pytest  # noqa: E402

from hcpagents import db  # noqa: E402
from hcpagents.aws import floci_up  # noqa: E402


def pytest_collection_modifyitems(config, items):
    if floci_up() and db.is_up():
        return
    skip = pytest.mark.skip(reason="Floci or Postgres is not running: make up")
    for item in items:
        if "floci" in item.keywords:
            item.add_marker(skip)
