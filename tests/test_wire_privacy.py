"""What leaves for the model client is checked at the last step, not one step before it."""

import asyncio

import pytest

from hcpagents import agents, cases, infra, world

pytestmark = pytest.mark.floci


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def _secrets() -> list[str]:
    """Every value of a doctor that must never reach the wire: name, surname, email, ids and the four channel records."""
    found = []
    for doctor in world.hcp_world()["hcp"]:
        found += [doctor["id"], doctor["name"], doctor["name"].split()[-1], doctor["email"], doctor["registry_id"]]
        found += list(doctor["records"].values())
    return found


def test_no_doctor_name_email_phone_or_id_reaches_the_model_client(monkeypatch):
    sent = []
    real = agents._call_on

    async def recorder(model, agent, user_prompt, *rest):
        sent.append(user_prompt)
        return await real(model, agent, user_prompt, *rest)

    monkeypatch.setattr(agents, "_call_on", recorder)
    for inquiry in world.inquiries():
        try:
            asyncio.run(cases.run(inquiry["id"]))
        except agents.MissingRecording:
            continue
    assert len(sent) > 5, "the recorder saw too few calls to prove anything"
    leaks = [(secret, prompt[:60]) for prompt in sent for secret in _secrets() if secret in prompt]
    assert leaks == []
