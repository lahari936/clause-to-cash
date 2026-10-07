from typing import Any

import anthropic

from app.config import get_settings

_client: anthropic.Anthropic | None = None


def call_tool(
    system: str, messages: list[dict[str, Any]], tool: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Force one tool call; return (tool_use_id, tool input)."""
    global _client
    s = get_settings()
    _client = _client or anthropic.Anthropic(api_key=s.anthropic_api_key)
    resp = _client.messages.create(  # type: ignore[call-overload]
        model=s.llm_model,
        max_tokens=8192,
        system=system,
        messages=messages,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.id, dict(block.input)
    raise RuntimeError("model returned no tool_use block")
