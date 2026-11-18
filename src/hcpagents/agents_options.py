"""The Agent SDK options for one live call. They keep the call isolated and pinned to one model."""

import json
import os
import sys

from hcpagents import world
from hcpagents.agents_spec import AGENTS, MODEL, PROMPT_VERSION
from hcpagents.agents_tools import checked_output, run_tool
from hcpagents.guards import audit_entry, post_tool, pre_tool


def gateway_env(agent: str, case: dict) -> dict:
    """Every live call goes through the AI gateway with this tenant's key, not the real key (ADR 0019)."""
    url = os.environ.get("MI_GATEWAY")
    if not url:
        raise RuntimeError("Live calls go through the AI gateway: set MI_GATEWAY, or run inside `gateway.embedded()`")
    from hcpagents import gateway

    return {"ANTHROPIC_BASE_URL": url, "ANTHROPIC_API_KEY": gateway.key_for(world.current_tenant(), agent),
            "ANTHROPIC_CUSTOM_HEADERS": f"x-mi-case: {case['id']}\nx-mi-release: {gateway.release()}\nx-mi-prompt-version: {PROMPT_VERSION}"}


def _cli_stderr(line: str) -> None:
    # The bundled CLI has no price for this model and says so on every call. Spend prices it instead.
    if "unrecognized_model" not in line:
        print(line, file=sys.stderr)


def _text_result(tool_name: str, args: dict, case: dict, store: dict, audit) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(checked_output(tool_name, args, case, store, audit))}]}


def _hook(agent: str, case: dict, store: dict, authorize, audit, tool_calls: list):
    async def check(payload, tool_use_id, context):
        name, tool_input = payload["tool_name"], payload["tool_input"]
        allowed, reason = pre_tool(agent, name, tool_input, case, store, authorize)
        returned = []
        if allowed:
            kept, _ = post_tool(run_tool(store, name, tool_input), case, store)
            returned = [found["block_id"] for found in kept]
        tool_calls.append({"tool": name, "input": tool_input, "allowed": allowed, "reason": reason, "returned": returned})
        audit(audit_entry(agent, name, tool_input, allowed, reason, returned))
        if allowed:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": reason}}

    return check


def _tool_options(agent: str, case: dict, store: dict, authorize, audit, tool_calls: list) -> dict:
    from claude_agent_sdk import HookMatcher, create_sdk_mcp_server, tool

    @tool("search_approved_content", "Search current approved content blocks for one product and country with a question in plain words.",
          {"product": str, "country": str, "query": str})
    async def search_tool(args):
        return _text_result("mcp__mi__search_approved_content", args, case, store, audit)

    @tool("get_block", "Read one current approved content block by id.", {"block_id": str})
    async def get_tool(args):
        return _text_result("mcp__mi__get_block", args, case, store, audit)

    check = _hook(agent, case, store, authorize, audit, tool_calls)
    return {
        "mcp_servers": {"mi": create_sdk_mcp_server("mi", "1.0.0", [search_tool, get_tool])},
        "allowed_tools": sorted({"mcp__mi__search_approved_content", "mcp__mi__get_block"}),
        "hooks": {"PreToolUse": [HookMatcher(matcher="mcp__mi__.*", hooks=[check])]},
    }


def options(model: str, agent: str, case: dict, store: dict, authorize, audit, tool_calls: list):
    from claude_agent_sdk import ClaudeAgentOptions

    spec = AGENTS[agent]
    extra = {}
    if spec.get("tools"):
        extra = _tool_options(agent, case, store, authorize, audit, tool_calls)
    return ClaudeAgentOptions(
        model=model,
        system_prompt=spec["system"],
        tools=[],
        max_turns=spec["max_turns"],
        output_format={"type": "json_schema", "schema": spec["schema"]},
        # This call stays alone. It has no user settings, plugins, servers or slash commands.
        # Each background call uses the same model.
        setting_sources=[],
        strict_mcp_config=True,
        plugins=[],
        extra_args={"disable-slash-commands": None},
        env={
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
            "ANTHROPIC_SMALL_FAST_MODEL": MODEL,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            **gateway_env(agent, case),
        },
        # A backstop only. The CLI misprices this model, so the real cap is Spend.
        max_budget_usd=0.5,
        stderr=_cli_stderr,
        **extra,
    )
