from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.llm.provider import structured


class Answer(BaseModel):
    city: str
    population: int


def _fake(replies: list[dict[str, Any]]) -> tuple[Any, list[list[dict[str, Any]]]]:
    seen: list[list[dict[str, Any]]] = []

    def call(system: str, messages: list[dict[str, Any]], tool: dict[str, Any]) -> Any:
        assert tool["input_schema"]["properties"].keys() == {"city", "population"}
        seen.append(list(messages))
        return f"tu_{len(seen)}", replies[len(seen) - 1]

    return call, seen


def test_valid_first_try() -> None:
    call, seen = _fake([{"city": "Paris", "population": 2}])
    assert structured("q", Answer, caller=call) == Answer(city="Paris", population=2)
    assert len(seen) == 1


def test_retry_feeds_error_back_once() -> None:
    call, seen = _fake([{"city": "Paris"}, {"city": "Paris", "population": 2}])
    assert structured("q", Answer, caller=call).population == 2
    assert len(seen) == 2
    feedback = seen[1][-1]["content"][0]
    assert feedback["type"] == "tool_result" and feedback["is_error"]
    assert "population" in feedback["content"]


def test_gives_up_after_one_retry() -> None:
    call, seen = _fake([{"city": "Paris"}, {"city": "Paris"}])
    with pytest.raises(ValidationError):
        structured("q", Answer, caller=call)
    assert len(seen) == 2


@pytest.mark.live
def test_live_anthropic() -> None:
    ans = structured("What is the capital of France and its population in millions?", Answer)
    assert ans.city.lower() == "paris"
