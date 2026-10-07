from pathlib import Path

import pymupdf
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Dispute, Invoice, Milestone
from app.main import app
from app.services import invoicing, milestones
from tests.conftest import approved_contract, mock_invoicing

api = TestClient(app)
ARTIFACTS = Path(__file__).parents[2] / "artifacts"


def _paid_invoice(db, llm, pp):  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm)
    llm.on(
        "AcceptanceResult",
        {"meets_criteria": True, "gaps": [], "summary_for_client": "Figma file covers all pages."},
    )
    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 1)).one()
    milestones.deliver(db, m, "Figma design system shared", ["https://figma.com/file/abc"])
    milestones.accept(db, m, "owner")
    inv = db.scalars(select(Invoice)).one()
    pp.get(f"/v2/invoicing/invoices/{inv.paypal_invoice_id}").respond(
        json={"status": "PAID", "payments": {"paid_amount": {"value": "4000.00"}}}
    )
    invoicing.sync_invoice(db, inv)
    db.commit()
    return inv


def test_evidence_pack_cites_contract_and_saves_pdf(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _paid_invoice(db, llm, pp)
    seen: list[str] = []

    def pack(facts: str) -> dict[str, str]:
        seen.append(facts)
        quote = next(line for line in facts.splitlines() if line.startswith("Clause (milestone)"))
        return {
            "evidence_markdown": f"# Summary\nDelivered and accepted.\n## Contract terms\n- {quote}",
            "proposed_response": "Work was delivered per the contract.",
        }

    llm.on("Pack", pack)
    r = api.post("/disputes/demo", json={"invoice_id": inv.id})
    assert r.status_code == 201, r.text
    facts = seen[0]
    assert "Milestone 1 - Discovery and design system" in facts  # verbatim clause
    assert "Figma design system shared" in facts and "payment_received" in facts

    d = db.scalars(select(Dispute)).one()
    assert d.dry_run and d.invoice_id == inv.id
    pdf = api.get(f"/disputes/{d.id}/pdf").content
    assert pdf.startswith(b"%PDF")
    text = "".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
    assert "Discovery and design system" in text
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "evidence_pack_demo.pdf").write_bytes(pdf)

    r = api.post(f"/disputes/{d.id}/submit", json={"by": "owner"})
    assert "dry run" in r.json()["status"]
    db.expire_all()
    assert db.get(Milestone, inv.milestone_id).status == "disputed"


def test_pack_falls_back_when_llm_down(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _paid_invoice(db, llm, pp)  # no "Pack" route -> agent fails -> deterministic pack
    r = api.post("/disputes/demo", json={"invoice_id": inv.id})
    d = db.get(Dispute, r.json()["id"])
    assert "Clause (milestone)" in d.evidence_md and d.evidence_pdf.startswith(b"%PDF")
