"""Three agents on the Claude Agent SDK. They use claude-haiku-5-5 or claude-sonnet-5-5 and nothing else.

The safety agent spots possible harm to a patient and quotes the words.
The triage agent sorts each question.
The assembler agent searches approved content with two tools. It picks block ids for each question.

None of them writes text a doctor reads. Each call is recorded. Replay is the default, and it runs the saved tool calls again through the same guards.
So the demo, the evals and `make check` cost nothing.
LIVE=1 calls the model and saves the recording. A spend cap, worked out from tokens, limits it.
"""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime

from hcpagents import router, world
from hcpagents.agents_options import gateway_env, options as _options
from hcpagents.agents_spec import AGENT_TASK, AGENTS, MODEL, PROMPT_VERSION
from hcpagents.agents_tools import SEARCH_RESULTS, checked_output, get_block, run_tool, search
from hcpagents.guards import audit_entry, pre_tool
from hcpagents.router import HAIKU, SONNET

__all__ = ["AGENTS", "AGENT_TASK", "ALLOWED_MODELS", "AgentFailed", "BudgetError", "EscalateToHuman", "HAIKU", "MODEL",
           "MissingRecording", "ModelPolicyError", "PRICES", "PROMPT_VERSION", "RECORDINGS", "SEARCH_RESULTS", "SONNET",
           "SPEND", "Spend", "_options", "call", "check_models", "cost_usd", "gateway_env", "get_block", "live",
           "recording_key", "run_sync", "run_tool", "search", "untrusted"]

ALLOWED_MODELS = frozenset({HAIKU, SONNET})
# US dollars per million tokens. The bundled CLI does not know these prices, so its own
# cost figure is wrong. This is the number the budget is enforced on.
PRICES = {
    HAIKU: {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.20},
    SONNET: {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 4.00},
}
RECORDINGS = world.ROOT / "recordings"
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


class ModelPolicyError(RuntimeError):
    """A call used a model outside ALLOWED_MODELS."""


class AgentFailed(RuntimeError):
    """A live run ended without a valid structured answer. The router may retry it on Sonnet."""


class EscalateToHuman(RuntimeError):
    """The router has no model left to try, or no budget for one. The case goes to review.
    The calls already made on the way here are in attempts, so they are still counted against the caps."""

    attempts = 0


class BudgetError(RuntimeError):
    """A live call would exceed the spend cap."""


class MissingRecording(RuntimeError):
    """Replay found no recording for this exact prompt."""


def live() -> bool:
    return os.environ.get("LIVE") == "1"


def cost_usd(usage: dict, model: str = MODEL) -> float:
    price = PRICES[model]
    return round(
        (usage.get("input_tokens", 0) * price["input"]
         + usage.get("output_tokens", 0) * price["output"]
         + usage.get("cache_read_input_tokens", 0) * price["cache_read"]
         + usage.get("cache_creation_input_tokens", 0) * price["cache_write"]) / 1_000_000,
        6,
    )


def check_models(model_usage: dict | None) -> None:
    # Step 1: Find every model the run used that is not on the list.
    others = sorted(set(model_usage or {}) - ALLOWED_MODELS)
    # Step 2: Refuse the run and name those models.
    if others:
        raise ModelPolicyError(f"Run used {others}; only {sorted(ALLOWED_MODELS)} are allowed")


class Spend:
    """Live spend for this process, checked before every live call."""

    def __init__(self):
        budget = world.autonomy_seed()["budget"]
        self.per_case, self.per_session = budget["per_case_usd"], budget["per_session_usd"]
        self.session = 0.0
        self.cases: dict[str, float] = {}

    def check(self, case_id: str) -> None:
        if self.session >= self.per_session:
            raise BudgetError(f"Session spend ${self.session:.4f} reached the ${self.per_session} cap")
        if self.cases.get(case_id, 0.0) >= self.per_case:
            raise BudgetError(f"Case {case_id} spend reached the ${self.per_case} cap")

    def add(self, case_id: str, usd: float) -> None:
        self.session += usd
        self.cases[case_id] = self.cases.get(case_id, 0.0) + usd


SPEND = Spend()


def untrusted(text: str) -> str:
    """Inquiry text goes in as safe data. It is never a set of orders."""
    safe = text.replace("<", "&lt;").replace(">", "&gt;")
    return f"<inquiry_data>\n{json.dumps(safe, ensure_ascii=False)}\n</inquiry_data>"


def recording_key(agent: str, user_prompt: str, model: str = MODEL) -> str:
    spec = AGENTS[agent]
    raw = json.dumps([agent, PROMPT_VERSION, model, spec["system"], spec["schema"], user_prompt], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ---------------------------------------------------------------- calls

async def call(agent: str, user_prompt: str, case: dict, store: dict, authorize, audit) -> dict:
    """Run one agent on the model the router picks.

    If a live run gives no valid answer, it is tried once more on Sonnet. After that a human gets the case.
    """
    task, risk = AGENT_TASK[agent]
    prior: list[router.Outcome] = []
    while True:
        budget_left = SPEND.per_case - SPEND.cases.get(case["id"], 0.0)
        decision = router.route(task, risk, budget_left, tuple(prior))
        if decision.model is None:
            gave_up = EscalateToHuman(f"{agent}: {decision.reason}")
            gave_up.attempts = len(prior)
            raise gave_up
        try:
            reply = await _call_on(decision.model, agent, user_prompt, case, store, authorize, audit)
            return reply | {"routing": decision.reason, "attempts": len(prior) + 1}
        except AgentFailed:
            prior.append(router.Outcome(decision.model, router.SCHEMA_FAILURE))


async def _record_live(model: str, agent: str, user_prompt: str, case: dict, store: dict, authorize, audit) -> dict:
    key = recording_key(agent, user_prompt, model)
    path = RECORDINGS / agent / f"{key}.json"
    SPEND.check(case["id"])
    recording = await _live(model, agent, user_prompt, case, store, authorize, audit)
    SPEND.add(case["id"], recording["cost_usd"])
    path.parent.mkdir(parents=True, exist_ok=True)
    recording |= {"agent": agent, "key": key, "prompt_version": PROMPT_VERSION, "model": model,
                  "user_prompt": user_prompt, "recorded_at": datetime.now(UTC).isoformat(timespec="seconds")}
    path.write_text(json.dumps(recording, indent=1, ensure_ascii=False) + "\n")
    return recording | {"mode": "live"}


def _replay(agent: str, user_prompt: str, model: str, case: dict, store: dict, authorize, audit) -> dict:
    key = recording_key(agent, user_prompt, model)
    path = RECORDINGS / agent / f"{key}.json"
    if not path.exists():
        raise MissingRecording(f"No recording for {agent} {key}. Run with LIVE=1 to record it.")
    recording = json.loads(path.read_text())
    check_models(recording.get("model_usage"))
    for tool_call in recording["tool_calls"]:
        allowed, reason = pre_tool(agent, tool_call["tool"], tool_call["input"], case, store, authorize)
        returned = []
        if allowed:
            kept = checked_output(tool_call["tool"], tool_call["input"], case, store, audit)
            returned = [found["block_id"] for found in kept]
        audit(audit_entry(agent, tool_call["tool"], tool_call["input"], allowed, reason, returned))
        tool_call |= {"allowed_now": allowed, "returned_now": returned}
    return recording | {"mode": "replay"}


async def _call_on(model: str, agent: str, user_prompt: str, case: dict, store: dict, authorize, audit) -> dict:
    if live():
        return await _record_live(model, agent, user_prompt, case, store, authorize, audit)
    return _replay(agent, user_prompt, model, case, store, authorize, audit)


async def _live(model: str, agent: str, user_prompt: str, case: dict, store: dict, authorize, audit) -> dict:
    from claude_agent_sdk import ResultMessage, query

    tool_calls: list = []
    sdk_options = _options(model, agent, case, store, authorize, audit, tool_calls)
    result = None
    async for message in query(prompt=user_prompt, options=sdk_options):
        if isinstance(message, ResultMessage):
            result = message
    if result is None or result.subtype != "success" or result.structured_output is None:
        reason = "no result"
        if result:
            reason = result.subtype
        raise AgentFailed(f"{agent} did not finish: {reason}")
    check_models(result.model_usage)
    usage = {name: (result.usage or {}).get(name, 0) for name in USAGE_KEYS}
    return {"output": result.structured_output, "tool_calls": tool_calls, "usage": usage,
            "model_usage": {name: {"inputTokens": count.get("inputTokens"), "outputTokens": count.get("outputTokens")}
                            for name, count in (result.model_usage or {}).items()},
            "cost_usd": cost_usd(usage, model)}


def run_sync(coroutine):
    return asyncio.run(coroutine)
