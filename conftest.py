import pytest

from hcpagents.aws import floci_up


def pytest_collection_modifyitems(config, items):
    if floci_up():
        return
    skip = pytest.mark.skip(reason="Floci is not running: make up")
    for item in items:
        if "floci" in item.keywords:
            item.add_marker(skip)
