"""The handoff teams run on their own. A Temporal task calls them, so no event waits for a person to start them."""

import asyncio
import inspect

import pytest

from hcpagents import activities, durable, events, handoff_workers, store, workflows
from tests.test_flow import fresh  # noqa: F401 - fresh is an autouse fixture


def test_every_handoff_handler_is_reached_from_a_registered_task_that_the_steward_runs():
    assert activities.handoff_tick in durable.ACTIVITIES
    assert "handoff_workers.run_once()" in inspect.getsource(activities.handoff_tick)
    assert 'execute_activity("handoff_tick"' in inspect.getsource(workflows.ContentStewardWorkflow)
    reached = set(handoff_workers.HANDLERS)
    for queue_type in ("ReviewNeeded", "ReviewOverdue", "SafetySignal"):
        assert queue_type in reached


@pytest.mark.floci
def test_the_handoff_task_drains_a_review_event_into_the_reviewer_queue():
    events.publish("ReviewNeeded", {"case": "inq-sched", "country": "DE", "why": "Off label"})
    handled = asyncio.run(activities.handoff_tick({}))
    assert handled["mi-medical-review"] == 1
    assert store.get("mi-reviewer-queue", "review-inq-sched")["status"] == "waiting"
