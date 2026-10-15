"""Guard tool calls with Cedar: two independent checks stand between an agent and another country's content."""

import pytest

from hcpagents import authz, guards, infra, world

pytestmark = pytest.mark.floci

STORE = {b["id"]: b for b in world.blocks()}
CASE = {"id": "lab-cedar", "country": "DE", "product": "VEL"}
SEARCH = "mcp__mi__search_approved_content"


@pytest.fixture(scope="module", autouse=True)
def policies():
    infra.policy_store()  # loads policies/cedar as it is on disk now


def test_the_cases_own_content_is_allowed_by_both_checks():
    ok, why = guards.pre_tool("assembler", SEARCH, {"country": "DE", "product": "VEL", "topic": "dosing"}, CASE, STORE,
                              authz.agent_can_call)
    assert ok and why == "Verified Permissions: ALLOW (agents.cedar)"


def test_cedar_refuses_another_country_even_if_the_code_guard_were_bypassed():
    ok, why = authz.agent_can_call("assembler", SEARCH, "US", "VEL", CASE)
    assert not ok and why.startswith("Verified Permissions: DENY")


def test_a_tool_off_the_allowlist_never_reaches_the_policy_store():
    asked = []
    ok, _ = guards.pre_tool("assembler", "Bash", {"command": "env"}, CASE, STORE, lambda *a: asked.append(a) or (True, ""))
    assert not ok and not asked
