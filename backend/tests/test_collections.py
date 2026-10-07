import json
from datetime import timedelta
from decimal import Decimal as D

import respx
from sqlalchemy import select

from app.db.models import GuardEvent, Invoice, Milestone
from app.money import dates
from app.services import collections, milestones
from tests.conftest import approved_contract, mock_invoicing


def _sent_invoice(db, llm, pp):  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", {"meets_criteria": True, "gaps": [], "summary_for_client": "ok"})
    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 1)).one()
    milestones.deliver(db, m, "done", [])
    milestones.accept(db, m, "owner")
    db.commit()
    return db.scalars(select(Invoice)).one()


def test_not_overdue_does_nothing(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    _sent_invoice(db, llm, pp)
    assert collections.run(db) == []


def test_reminder_in_grace_then_contract_correct_late_fee(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _sent_invoice(db, llm, pp)
    remind = pp.routes[3]
    # northwind: net 15, 1.5%/month after 5 grace days, cap 500
    dates.set_today(inv.due_date + timedelta(days=3))
    out = collections.run(db)
    assert [a["kind"] for a in out] == ["remind"] and out[0]["decision"] == "ALLOW"
    assert remind.call_count == 1  # LLM unavailable -> template message still sent
    assert collections.run(db) == []  # once per day

    dates.set_today(inv.due_date + timedelta(days=6))
    out = collections.run(db)
    assert [(a["kind"], a["decision"]) for a in out] == [
        ("remind", "ALLOW"),
        ("late_fee_invoice", "ALLOW"),
    ]
    fee = db.scalars(select(Invoice).where(Invoice.kind == "late_fee")).one()
    assert fee.amount == D("60.00") and fee.base_invoice_id == inv.id  # 1.5% of 4000
    body = json.loads(pp.routes[1].calls[-1].request.read())
    assert body["items"][0]["unit_amount"]["value"] == "60.00"
    assert "1.5% per month" in body["items"][0]["description"]  # the clause rides along

    dates.set_today(inv.due_date + timedelta(days=60))
    out = collections.run(db)
    assert [a["kind"] for a in out] == ["remind"]  # only one late fee per invoice


def test_hand_crafted_wrong_late_fee_denied(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    from app.guard import Action
    from app.services.actions import execute

    inv = _sent_invoice(db, llm, pp)
    dates.set_today(inv.due_date + timedelta(days=6))
    a = Action(
        "late_fee_invoice",
        inv.contract_id,
        D("400.00"),
        "USD",
        "client@test.example",
        invoice_id=inv.id,
    )
    out = execute(db, a, "test")
    assert out.decision.decision == "DENY" and out.decision.rule_ids == ["G6"]
    assert db.scalars(select(GuardEvent).where(GuardEvent.decision == "DENY")).one()
