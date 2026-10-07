from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ingest.sections import render_for_llm, split_sections
from app.llm.provider import structured
from app.schemas.extraction import Cited, ContractExtraction

PROMPT = (Path(__file__).parent / "prompts" / "extractor.md").read_text()


def extract(pages: list[str]) -> ContractExtraction:
    text = render_for_llm(split_sections(pages))
    return structured(f"Contract text:\n\n{text}", ContractExtraction, system=PROMPT)


@dataclass
class FieldItem:
    path: str
    value: Any  # JSON-able, without the citation
    cite: Cited | None


def field_items(x: ContractExtraction) -> list[FieldItem]:
    """The reviewable fields. Object fields (a party, a milestone) are reviewed as one unit."""
    d = x.model_dump(mode="json")

    def obj(o: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in o.items() if k != "cite"}

    items = [
        FieldItem("currency", x.currency, x.total_cite),
        FieldItem("total_amount", d["total_amount"], x.total_cite),
        FieldItem("net_days", x.net_days, x.net_days_cite),
        FieldItem("deposit_amount", d["deposit_amount"], x.total_cite),
        FieldItem("late_fee", obj(d["late_fee"]), x.late_fee.cite),
        FieldItem("auto_accept_days", x.auto_accept_days, x.auto_accept_cite),
    ]
    items += [
        FieldItem(f"parties[{i}]", obj(p), x.parties[i].cite) for i, p in enumerate(d["parties"])
    ]
    items += [
        FieldItem(f"milestones[{i}]", obj(m), x.milestones[i].cite)
        for i, m in enumerate(d["milestones"])
    ]
    return items


def apply_override(extraction: dict[str, Any], path: str, value: Any) -> None:
    """Write a reviewed value back into the extraction JSON at `path` (keeps the citation)."""
    if "[" in path:
        key, idx = path[:-1].split("[")
        target = extraction[key][int(idx)]
        target.update({k: v for k, v in value.items() if k != "cite"})
    elif isinstance(extraction.get(path), dict):
        extraction[path].update({k: v for k, v in value.items() if k != "cite"})
    else:
        extraction[path] = value
