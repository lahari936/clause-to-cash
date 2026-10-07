from pathlib import Path

from app.ingest.pdf import page_texts
from app.ingest.sections import split_sections

PDFS = Path(__file__).parents[1] / "evals" / "contracts"


def _sections(name: str) -> dict[str, int]:
    pages = page_texts((PDFS / name).read_bytes())
    assert len(pages) == 2
    return {s.ref: s.page for s in split_sections(pages)}


def test_northwind_sections_and_pages() -> None:
    secs = _sections("01_northwind_web.pdf")
    assert {"1", "3", "4", "5", "6", "7", "8"} <= secs.keys()
    assert secs["1"] == 1 and secs["5"] == 2  # payment terms land on page 2
    assert secs["4"] < secs["8"] or secs["4"] == secs["8"]


def test_no_subcontractor_section_when_absent() -> None:
    secs = _sections("02_eur_fixed_fee.pdf")
    assert "6" not in secs and "5" in secs


def test_ligatures_expanded() -> None:
    text = "".join(page_texts((PDFS / "02_eur_fixed_fee.pdf").read_bytes()))
    assert "finance@baumhaus.example" in text and "ﬁ" not in text
