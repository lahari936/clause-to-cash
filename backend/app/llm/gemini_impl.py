"""Gemini via REST (free tier). Same call_tool contract as anthropic_impl."""

import json
from typing import Any

import httpx

from app.config import get_settings

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _parts(content: Any) -> str:
    if isinstance(content, str):
        return content
    out = []
    for block in content:
        if block["type"] == "tool_use":
            out.append(json.dumps(block["input"]))
        elif block["type"] == "tool_result":
            out.append(str(block["content"]))
        else:
            out.append(str(block.get("text", "")))
    return "\n".join(out)


def call_tool(
    system: str, messages: list[dict[str, Any]], tool: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    s = get_settings()
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": _parts(m["content"])}],
            }
            for m in messages
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": tool["input_schema"],
            "temperature": 0,
        },
    }
    r = httpx.post(
        URL.format(model=s.llm_model),
        headers={"x-goog-api-key": s.gemini_api_key},
        json=body,
        timeout=120,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return "gemini", json.loads(text)
