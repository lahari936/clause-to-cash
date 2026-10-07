from pathlib import Path

import pytest

from app.agents import checker
from app.agents.extractor import field_items
from app.agents.validators import quote_score, validate
from app.ingest.pdf import page_texts
from app.schemas.extraction import ContractExtraction
from app.services import contracts
from tests.conftest import PDFS, gold, ok_verdicts


def _load(slug: str) -> tuple[ContractExtraction, list[str]]:
    return (
        ContractExtraction.model_validate(gold(slug)),
        page_texts((PDFS / f"{slug}.pdf").read_bytes()),
    )


def test_inconsistent_contract_flagged_by_validator() -> None:
    x, pages = _load("06_inconsistent_total")
    flags = validate(x, pages)
    assert set(flags) == {"total_amount"}
    assert "9000" in flags["total_amount"] and "10000" in flags["total_amount"]


@pytest.mark.parametrize("slug", sorted(p.stem for p in Path(PDFS).glob("*.pdf")))
def test_consistent_gold_has_no_flags(slug: str) -> None:
    x, pages = _load(slug)
    assert set(validate(x, pages)) == ({"total_amount"} if slug.startswith("06") else set())


def test_fabricated_quote_flagged() -> None:
    x, pages = _load("01_northwind_web")
    x.late_fee.cite.quote = "Late fees are 10% per day with no cap."  # type: ignore[union-attr]
    assert "late_fee" in validate(x, pages)
    assert quote_score(x.total_cite.quote, pages[x.total_cite.page - 1]) == 1.0


def test_checker_only_sees_cited_page(llm) -> None:  # type: ignore[no-untyped-def]
    x, pages = _load("01_northwind_web")
    llm.on("CheckBatch", ok_verdicts)
    checker.check(field_items(x), pages)
    prompt = llm.calls[0][1]
    # context-starved: every item block carries one page, never the whole contract at once
    assert prompt.count("text:\n") == len(
        [f for f in field_items(x) if f.value is not None and f.cite]
    )
    assert "Notices must be in writing" not in prompt.split("### Item 1")[0]


def test_checker_wrong_and_missing_verdicts(llm) -> None:  # type: ignore[no-untyped-def]
    x, pages = _load("01_northwind_web")
    llm.on(
        "CheckBatch",
        {
            "results": [
                {
                    "path": "net_days",
                    "verdict": "wrong",
                    "reason": "page says 30",
                    "corrected": "30",
                }
            ]
        },
    )
    out = checker.check(field_items(x), pages)
    assert out["net_days"].verdict == "wrong"
    assert out["total_amount"].verdict == "unsupported"  # no verdict returned -> flagged, not ok


def test_flags_block_approval_until_resolved(db, llm) -> None:  # type: ignore[no-untyped-def]
    c = contracts.upload(db, "Sable", (PDFS / "06_inconsistent_total.pdf").read_bytes())
    llm.on("ContractExtraction", gold("06_inconsistent_total"))
    llm.on("CheckBatch", ok_verdicts)
    contracts.run_extraction(db, c)
    flagged = [f.path for f in contracts.fields(db, c.id) if contracts.is_flagged(f)]
    assert flagged == ["total_amount"]
    with pytest.raises(contracts.ReviewError):
        contracts.approve(db, c, "owner")
    contracts.override(db, c, "total_amount", "9000.00")  # human fixes the total
    m = contracts.approve(db, c, "owner")
    assert m.rules_json["total_amount"] == "9000.00" and c.status == "approved"


def test_low_confidence_is_flagged(db, llm) -> None:  # type: ignore[no-untyped-def]
    g = gold()
    g["net_days_cite"]["confidence"] = 0.4
    c = contracts.upload(db, "NW", (PDFS / "01_northwind_web.pdf").read_bytes())
    llm.on("ContractExtraction", g)
    llm.on("CheckBatch", ok_verdicts)
    contracts.run_extraction(db, c)
    assert [f.path for f in contracts.fields(db, c.id) if contracts.is_flagged(f)] == ["net_days"]
