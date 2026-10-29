"""Event delivery is at least once, so consumers are idempotent, retry, and park what keeps failing (ADR 0020)."""

import uuid

import pytest

from hcpagents import events, infra, world

pytestmark = pytest.mark.floci

QUEUE, TYPE = "mi-content-invalidation", "ContentWithdrawn"


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def send(**detail) -> str:
    return events.publish(TYPE, {"block": "b1", **detail}, key=uuid.uuid4().hex)


def test_an_event_published_twice_under_one_key_is_handled_once():
    seen = []
    key = uuid.uuid4().hex
    events.publish(TYPE, {"block": "b1"}, key=key)
    events.publish(TYPE, {"block": "b1"}, key=key)
    assert events.consume(QUEUE, seen.append) == 1
    assert [d["event_id"] for d in seen] == [key]


def test_a_handler_that_fails_once_is_tried_again():
    calls = []

    def flaky(detail):
        calls.append(detail["event_id"])
        if len(calls) == 1:
            raise RuntimeError("first try fails")

    event_id = send()
    assert events.consume(QUEUE, flaky) == 1
    assert calls == [event_id, event_id]
    assert not [d for d in events.dead_letters() if d["event_id"] == event_id]


def test_an_event_that_fails_every_attempt_is_parked_with_its_error_and_leaves_the_queue():
    def broken(detail):
        raise RuntimeError("downstream is down")

    event_id = send()
    assert events.consume(QUEUE, broken) == 0
    [parked] = [d for d in events.dead_letters() if d["event_id"] == event_id]
    assert parked["attempts"] == events.MAX_ATTEMPTS and "downstream is down" in parked["error"]
    assert events.depth()[QUEUE] == 0


def test_a_parked_event_replays_once_and_its_handler_runs_again():
    def broken(detail):
        raise RuntimeError("down")

    event_id = send()
    events.consume(QUEUE, broken)
    [parked] = [d for d in events.dead_letters() if d["event_id"] == event_id]
    seen = []
    events.replay(parked["id"])
    assert events.consume(QUEUE, seen.append) == 1 and seen[0]["event_id"] == event_id
    assert not [d for d in events.dead_letters() if d["event_id"] == event_id]
    with pytest.raises(LookupError):
        events.replay(parked["id"])


def test_one_tenants_parked_events_are_invisible_to_another():
    def broken(detail):
        raise RuntimeError("down")

    with world.as_tenant("marlowe"):
        event_id = send()
    events.consume(QUEUE, broken)
    assert not [d for d in events.dead_letters() if d["event_id"] == event_id]
    with world.as_tenant("marlowe"):
        assert [d for d in events.dead_letters() if d["event_id"] == event_id]
