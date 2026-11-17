"""Guard tool calls with Cedar. Two separate checks stand between an agent and the content of another country."""

import pytest

from hcpagents import authz, guards, infra, world

pytestmark = pytest.mark.floci

STORE = {block["id"]: block for block in world.blocks()}
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

    def policy_that_allows(*arguments):
        asked.append(arguments)
        return True, ""

    ok, _ = guards.pre_tool("assembler", "Bash", {"command": "env"}, CASE, STORE, policy_that_allows)
    assert not ok and not asked
