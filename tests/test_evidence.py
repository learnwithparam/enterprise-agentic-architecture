"""The committed live evidence names the request key of every inquiry; an edit that changes a request names the inquiry."""

import asyncio
import json

import pytest

from hcpagents import agents, cases, evals, world

pytestmark = pytest.mark.floci


async def _stale(recorded: dict) -> list[str]:
    stale = []
    for inq in world.inquiries():
        try:
            key = evals.inquiry_key(await cases.run(inq["id"]))
        except agents.MissingRecording:
            key = None
        if recorded.get(inq["id"]) != key:
            stale.append(inq["id"])
    return stale


def test_live_evidence_fresh():
    evidence = json.loads(evals.EVIDENCE.read_text())
    assert evidence["model"] == agents.MODEL
    stale = asyncio.run(_stale(evidence["inquiries"]))
    assert not stale, f"stale or unrecorded: {stale}"
