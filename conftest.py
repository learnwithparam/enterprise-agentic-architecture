import pytest

from hcpagents import db
from hcpagents.aws import floci_up


def pytest_collection_modifyitems(config, items):
    if floci_up() and db.up():
        return
    skip = pytest.mark.skip(reason="Floci or Postgres is not running: make up")
    for item in items:
        if "floci" in item.keywords:
            item.add_marker(skip)
