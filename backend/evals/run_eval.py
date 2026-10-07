"""Field-level extraction eval against hand-checked gold.

--stage extractor : raw extractor accuracy.
default (full)    : extractor + validators + checker. A field counts as correct if its value is right,
                    or if it is wrong but flagged for human review (the pipeline caught it).
Run: python -m evals.run_eval [--stage extractor] --min-field-acc 0.9
"""

import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.agents.checker import CheckResult, check
from app.agents.extractor import extract, field_items
from app.agents.validators import validate
from app.ingest.pdf import page_texts
from app.schemas.extraction import ContractExtraction

HERE = Path(__file__).parent
OUT = HERE / "out"
KEYS = {
    "parties": ("role", "name", "email", "share_pct"),
    "milestones": ("seq", "amount", "due_date"),
    "late_fee": ("type", "value", "grace_days", "cap"),
}


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:
        return str(a).strip().lower() == str(b).strip().lower()


def _eq(path: str, pred: Any, gold: Any) -> bool:
    keys = next((v for k, v in KEYS.items() if path.startswith(k)), None)
    if keys and isinstance(gold, dict):
        return isinstance(pred, dict) and all(_same(pred.get(k), gold.get(k)) for k in keys)
    return _same(pred, gold)


def score(
    pred: ContractExtraction, gold: ContractExtraction, flagged: set[str]
) -> tuple[int, int, list[str]]:
    p = {f.path: f for f in field_items(pred)}
    ok, misses = 0, []
    for g in field_items(gold):
        f = p.get(g.path)
        good = f is not None and _eq(g.path, f.value, g.value)
        page_ok = g.cite is None or (
            f is not None and f.cite is not None and f.cite.page == g.cite.page
        )
        if (good and page_ok) or g.path in flagged:
            ok += 1
        else:
            misses.append(f"{g.path}: got {f.value if f else None!r} want {g.value!r}")
    return ok, len(field_items(gold)), misses


def run(stage: str, cached: bool) -> float:
    OUT.mkdir(exist_ok=True)
    total_ok = total = 0
    for pdf in sorted((HERE / "contracts").glob("*.pdf")):
        pages = page_texts(pdf.read_bytes())
        gold = ContractExtraction.model_validate_json(
            (HERE / "gold" / f"{pdf.stem}.json").read_text()
        )
        cache = OUT / f"{pdf.stem}.json"
        if cached and cache.exists():
            pred = ContractExtraction.model_validate_json(cache.read_text())
        else:
            pred = extract(pages)
            cache.write_text(pred.model_dump_json(indent=2))
            time.sleep(7)  # free-tier RPM
        flagged: set[str] = set()
        if stage == "full":
            flags = validate(pred, pages)
            saved = OUT / f"{pdf.stem}.flags.json"
            if cached and saved.exists():  # offline + reproducible: reuse recorded verdicts
                checked = json.loads(saved.read_text())["checker"]
                verdicts = {k: CheckResult(**v) for k, v in checked.items()}
            else:
                verdicts = check(field_items(pred), pages)
                time.sleep(7)
                saved.write_text(
                    json.dumps(
                        {
                            "validators": flags,
                            "checker": {k: v.model_dump() for k, v in verdicts.items()},
                        },
                        indent=2,
                    )
                )
            flagged = set(flags) | {p for p, r in verdicts.items() if r.verdict != "ok"}
            flagged |= {f.path for f in field_items(pred) if f.cite and f.cite.confidence < 0.7}
        ok, n, misses = score(pred, gold, flagged)
        total_ok, total = total_ok + ok, total + n
        print(f"{pdf.stem}: {ok}/{n}" + "".join(f"\n   miss {m}" for m in misses))
    acc = total_ok / total
    print(f"field accuracy ({stage}): {acc:.3f}")
    return acc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["extractor", "full"], default="full")
    ap.add_argument("--min-field-acc", type=float, default=0.9)
    ap.add_argument("--cached", action="store_true", help="reuse evals/out extractions")
    a = ap.parse_args()
    sys.exit(0 if run(a.stage, a.cached) >= a.min_field_acc else 1)


if __name__ == "__main__":
    main()
