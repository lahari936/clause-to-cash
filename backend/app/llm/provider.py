"""structured(prompt, schema) -> validated pydantic model, via forced tool use.

On a validation error the error is fed back to the model once, then we give up.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import get_settings

ToolCaller = Callable[[str, list[dict[str, Any]], dict[str, Any]], tuple[str, dict[str, Any]]]


def _caller() -> ToolCaller:
    provider = get_settings().llm_provider
    if provider == "anthropic":
        from app.llm.anthropic_impl import call_tool

        return call_tool
    # ponytail: Gemini impl not written yet; add app/llm/gemini_impl.py when it's needed.
    raise NotImplementedError(f"LLM_PROVIDER={provider} not implemented")


def structured[M: BaseModel](
    prompt: str,
    schema: type[M],
    system: str = "Answer only by calling the provided tool.",
    caller: ToolCaller | None = None,
) -> M:
    call = caller or _caller()
    tool = {
        "name": "submit",
        "description": f"Submit the {schema.__name__} result.",
        "input_schema": schema.model_json_schema(),
    }
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    tool_id, data = call(system, messages, tool)
    try:
        return schema.model_validate(data)
    except ValidationError as err:
        messages += [
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": tool_id, "name": "submit", "input": data}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "is_error": True,
                        "content": f"Validation failed, fix and resubmit:\n{err}",
                    }
                ],
            },
        ]
        _, data = call(system, messages, tool)
        return schema.model_validate(data)
