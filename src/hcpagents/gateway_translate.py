"""Turn Messages calls into Bedrock calls, and turn the replies back."""

import json
import secrets

from hcpagents.agents import HAIKU, SONNET

# Made from the model list, so that list stays the only one.
BEDROCK_MODELS = {model: f"anthropic.{model}-v1:0" for model in (HAIKU, SONNET)}
BEDROCK_STOP = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "max_tokens", "stop_sequence": "stop_sequence",
                "guardrail_intervened": "refusal", "content_filtered": "refusal"}


def _text(content) -> list[dict]:
    if isinstance(content, str):
        return [{"text": content}]
    return [{"text": block["text"]} for block in content if block.get("type") == "text"]


def _tool_result(block: dict) -> dict:
    status = "success"
    if block.get("is_error"):
        status = "error"
    return {"toolResult": {"toolUseId": block["tool_use_id"], "content": _text(block.get("content", "")), "status": status}}


def _block(block: dict) -> dict:
    if block["type"] == "text":
        return {"text": block["text"]}
    if block["type"] == "tool_use":
        return {"toolUse": {"toolUseId": block["id"], "name": block["name"], "input": block["input"]}}
    if block["type"] == "tool_result":
        return _tool_result(block)
    raise ValueError(f"Bedrock translation has no mapping for a {block['type']} block")


def _message(message: dict) -> dict:
    if isinstance(message["content"], str):
        return {"role": message["role"], "content": [{"text": message["content"]}]}
    return {"role": message["role"], "content": [_block(block) for block in message["content"]]}


def _tool_config(body: dict) -> dict:
    specs = [{"toolSpec": {"name": tool["name"], "description": tool.get("description", ""),
                           "inputSchema": {"json": tool["input_schema"]}}} for tool in body["tools"]]
    config = {"tools": specs}
    choice = body.get("tool_choice", {}).get("type")
    if choice == "any":
        config["toolChoice"] = {"any": {}}
    elif choice == "tool":
        config["toolChoice"] = {"tool": {"name": body["tool_choice"]["name"]}}
    return config


def to_converse(body: dict, model: str) -> dict:
    """Rewrite a Messages call for Bedrock."""
    out: dict = {"modelId": BEDROCK_MODELS[model],
                 "messages": [_message(message) for message in body["messages"]],
                 "inferenceConfig": {"maxTokens": body["max_tokens"]}}
    if body.get("system"):
        out["system"] = _text(body["system"])
    for source, target in (("temperature", "temperature"), ("top_p", "topP"), ("stop_sequences", "stopSequences")):
        if source in body:
            out["inferenceConfig"][target] = body[source]
    if body.get("tools"):
        out["toolConfig"] = _tool_config(body)
    return out


def from_converse(reply: dict, model: str) -> dict:
    """Rewrite a Bedrock reply for Messages."""
    content = []
    for block in reply["output"]["message"]["content"]:
        if "text" in block:
            content.append({"type": "text", "text": block["text"]})
        elif "toolUse" in block:
            tool = block["toolUse"]
            content.append({"type": "tool_use", "id": tool["toolUseId"], "name": tool["name"], "input": tool["input"]})
    return {"id": f"msg_bedrock_{secrets.token_hex(8)}", "type": "message", "role": "assistant", "model": model, "content": content,
            "stop_reason": BEDROCK_STOP.get(reply["stopReason"], "end_turn"), "stop_sequence": None,
            "usage": {"input_tokens": reply["usage"]["inputTokens"], "output_tokens": reply["usage"]["outputTokens"]}}


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps({'type': name} | data)}\n\n"


def _block_events(index: int, block: dict) -> list[str]:
    if block["type"] == "text":
        start = block | {"text": ""}
        delta = {"type": "text_delta", "text": block["text"]}
    else:
        start = block | {"input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    return [_event("content_block_start", {"index": index, "content_block": start}),
            _event("content_block_delta", {"index": index, "delta": delta}),
            _event("content_block_stop", {"index": index})]


def as_events(message: dict) -> bytes:
    """Replay a finished message as events."""
    started = message | {"content": [], "usage": {**message["usage"], "output_tokens": 1}}
    out = [_event("message_start", {"message": started})]
    for index, block in enumerate(message["content"]):
        out += _block_events(index, block)
    out += [_event("message_delta", {"delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
                                     "usage": {"output_tokens": message["usage"]["output_tokens"]}}), _event("message_stop", {})]
    return "".join(out).encode()
