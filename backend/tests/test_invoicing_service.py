import json
from decimal import Decimal as D

import respx
from sqlalchemy import select

from app.db.models import GuardEvent, Invoice, LedgerEntry, Milestone, Payout
from app.services import invoicing, milestones
from tests.conftest import approved_contract, mock_invoicing

ACCEPT = {"meets_criteria": True, "gaps": [], "summary_for_client": "Figma file shared."}


def first_milestone(db, c):  # type: ignore[no-untyped-def]
    return db.scalars(select(Milestone).where(Milestone.contract_id == c.id).order_by(Milestone.seq)).first()


def test_accept_creates_and_sends_exact_invoice(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", ACCEPT)
    m = first_milestone(db, c)
    milestones.deliver(db, m, "Figma link", ["https://figma.com/x"])
    out = milestones.accept(db, m, "owner")
    db.commit()

    assert out.decision.decision == "ALLOW"
    inv = db.scalars(select(Invoice)).one()
    assert (inv.status, inv.amount, inv.paypal_invoice_id) == ("SENT", D("4000.00"), "INV2-TEST-0001")
    assert m.status == "invoiced"
    body = json.loads(pp.routes[1].calls[0].request.read())
    assert body["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "4000.00"}
    assert body["primary_recipients"][0]["billing_info"]["email_address"] == "client@test.example"
    assert "Contract p." in body["detail"]["note"]  # the cited clause rides on the invoice
    assert pp.routes[1].calls[0].request.headers["PayPal-Request-Id"] == f"c2c-inv-{inv.id}"
    assert db.scalars(select(LedgerEntry.type)).all() == ["invoice_sent"]


def test_cannot_invoice_twice(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", ACCEPT)
    m = first_milestone(db, c)
    milestones.deliver(db, m, "done", [])
    milestones.accept(db, m, "owner")
    m.status = "accepted"  # try to sneak a second invoice
    again = invoicing.invoice_milestone(db, m, "owner")
    assert again.decision.decision == "DENY" and "G8" in again.decision.rule_ids
    assert len(db.scalars(select(Invoice)).all()) == 1


def test_undelivered_milestone_not_invoiced(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    c = approved_contract(db, llm)
    m = first_milestone(db, c)
    out = invoicing.invoice_milestone(db, m, "owner")  # status planned
    assert out.decision.decision == "DENY" and out.decision.rule_ids == ["G4"]
    assert len(pp.calls) == 0  # guard denied before any PayPal call


def test_paid_triggers_exact_share_payouts(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", ACCEPT)
    m = first_milestone(db, c)
    milestones.deliver(db, m, "done", [])
    milestones.accept(db, m, "owner")
    inv = db.scalars(select(Invoice)).one()
    pp.get(f"/v2/invoicing/invoices/{inv.paypal_invoice_id}").respond(
        json={"status": "PAID", "payments": {"paid_amount": {"value": "4000.00"}}}
    )
    invoicing.sync_invoice(db, inv)
    invoicing.sync_invoice(db, inv)  # idempotent
    db.commit()

    assert inv.status == "PAID" and m.status == "paid"
    payouts = db.scalars(select(Payout).order_by(Payout.id)).all()
    assert [(p.amount, p.status) for p in payouts] == [(D("600.00"), "SENT"), (D("400.00"), "SENT")]
    batch = json.loads(pp.routes[4].calls[0].request.read())
    assert [(i["receiver"], i["amount"]["value"]) for i in batch["items"]] == [
        ("ana@test.example", "600.00"), ("ben@test.example", "400.00")]
    assert len(pp.routes[4].calls) == 1  # one batch, and not re-sent on the second sync
    types = db.scalars(select(LedgerEntry.type).order_by(LedgerEntry.id)).all()
    assert types == ["invoice_sent", "payment_received", "payout_sent", "payout_sent"]
    allowed = db.scalars(select(GuardEvent).where(GuardEvent.action == "payout")).all()
    assert [e.decision for e in allowed] == ["ALLOW", "ALLOW"]
