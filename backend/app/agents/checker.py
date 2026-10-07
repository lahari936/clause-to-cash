"""Context-starved checker: each item sees only its own value and its cited page, never the full
contract or the extractor's reasoning. Items are batched into one call to stay inside free-tier
rate limits, but no item gets more context than its own page."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.agents.extractor import FieldItem
from app.llm.provider import structured

PROMPT = (Path(__file__).parent / "prompts" / "checker.md").read_text()


class CheckResult(BaseModel):
    path: str
    verdict: Literal["ok", "wrong", "unsupported"]
    reason: str
    corrected: str | None = None  # JSON text of the corrected value, if verdict == wrong


class CheckBatch(BaseModel):
    results: list[CheckResult]


def check(items: list[FieldItem], pages: list[str]) -> dict[str, CheckResult]:
    out: dict[str, CheckResult] = {}
    todo = []
    for it in items:
        if it.value is None or it.cite is None:
            continue  # nothing claimed, nothing to verify (absence is checked by validators)
        if not 1 <= it.cite.page <= len(pages):
            out[it.path] = CheckResult(path=it.path, verdict="unsupported", reason="no such page")
            continue
        todo.append(it)
    if not todo:
        return out
    blocks = [
        f"### Item {n}\npath: {it.path}\nvalue: {json.dumps(it.value)}\n"
        f'page {it.cite.page} text:\n"""\n{pages[it.cite.page - 1]}\n"""'
        for n, it in enumerate(todo, 1)
        if it.cite
    ]
    batch = structured("\n\n".join(blocks), CheckBatch, system=PROMPT)
    by_path = {r.path: r for r in batch.results}
    for it in todo:
        out[it.path] = by_path.get(it.path) or CheckResult(
            path=it.path, verdict="unsupported", reason="checker returned no verdict"
        )
    return out
