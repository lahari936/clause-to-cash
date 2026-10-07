"""Acceptance agent: three fixtures (meets / partial / missing). Offline tests check the evidence
reaches the model and the result is stored; the `live` test runs them against Gemini."""

from typing import Any

import pytest
from sqlalchemy import select

from app.agents import acceptance
from app.db.models import Milestone
from app.services import milestones
from tests.conftest import approved_contract

CRITERIA = ["Figma file shared with client", "Covers home, product and checkout pages"]
FIXTURES: dict[str, tuple[str, list[str], bool, int]] = {
    "meets": (
        "Shared the Figma file with Northwind; it covers home, product and checkout pages.",
        ["https://figma.com/file/abc"],
        True,
        0,
    ),
    "partial": (
        "Shared the Figma file. Home and product pages done; checkout next week.",
        ["https://figma.com/file/abc"],
        False,
        1,
    ),
    "missing": ("Worked on colors.", [], False, 2),
}


KEYWORDS = {CRITERIA[0]: "figma", CRITERIA[1]: "checkout pages"}


def _judge(prompt: str) -> dict[str, Any]:
    """Stand-in model: a criterion is met if its key phrase appears in the evidence."""
    evidence = prompt.split("Delivery notes:")[1].lower()
    gaps = [c for c, kw in KEYWORDS.items() if kw not in evidence]
    return {"meets_criteria": not gaps, "gaps": gaps, "summary_for_client": "summary"}


@pytest.mark.parametrize("case", FIXTURES)
def test_fixture_verdicts(llm, case: str) -> None:  # type: ignore[no-untyped-def]
    notes, links, meets, n_gaps = FIXTURES[case]
    llm.on("AcceptanceResult", _judge)
    r = acceptance.review("Discovery", CRITERIA, notes, links)
    assert (r.meets_criteria, len(r.gaps)) == (meets, n_gaps)
    prompt = llm.calls[0][1]
    assert all(c in prompt for c in CRITERIA) and notes in prompt


def test_delivery_stores_review_and_agent_failure_is_safe(db, llm) -> None:  # type: ignore[no-untyped-def]
    c = approved_contract(db, llm)
    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 1)).one()
    d = milestones.deliver(db, m, "Figma link", [])  # no AcceptanceResult route -> agent fails
    assert m.status == "delivered" and d.acceptance_json["meets_criteria"] is None
    llm.on("AcceptanceResult", _judge)
    d2 = milestones.deliver(db, m, FIXTURES["meets"][0], FIXTURES["meets"][1])
    assert d2.acceptance_json["meets_criteria"] is True


@pytest.mark.live
@pytest.mark.parametrize("case", FIXTURES)
def test_live_fixture_verdicts(case: str) -> None:
    notes, links, meets, _ = FIXTURES[case]
    assert (
        acceptance.review("Discovery and design system", CRITERIA, notes, links).meets_criteria
        == meets
    )
