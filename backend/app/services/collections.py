"""Overdue scan: remind once per day after due; after due + grace, one contract-correct late fee."""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Contract, Invoice
from app.guard import Action
from app.guard.engine import load_mandate
from app.money import dates, late_fee
from app.paypal.client import PayPalError
from app.services.actions import execute
from app.services.invoicing import client_party

log = logging.getLogger(__name__)


def run(db: Session, actor: str = "collections") -> list[dict[str, Any]]:
    today = dates.today()
    report: list[dict[str, Any]] = []
    overdue = db.scalars(
        select(Invoice).where(
            Invoice.kind == "milestone", Invoice.status == "SENT", Invoice.due_date < today
        )
    ).all()
    for inv in overdue:
        c = db.get(Contract, inv.contract_id)
        m = load_mandate(db, inv.contract_id)
        if not c or not c.currency or not m:
            continue
        payee = client_party(db, c.id).paypal_email or ""
        acts = []
        if inv.reminded_on != today:
            acts.append(Action("remind", c.id, Decimal(0), c.currency, payee, invoice_id=inv.id))
        assert inv.due_date
        fee = late_fee.compute(m.late_fee, inv.amount, inv.due_date, today)
        has_fee = db.scalar(
            select(Invoice.id).where(Invoice.base_invoice_id == inv.id, Invoice.status != "FAILED")
        )
        if fee > 0 and not has_fee:  # one late fee per invoice (G8 would deny a second anyway)
            acts.append(Action("late_fee_invoice", c.id, fee, c.currency, payee, invoice_id=inv.id))
        for a in acts:
            try:
                out = execute(db, a, actor)
                report.append({"invoice_id": inv.id, "kind": a.kind, **out.to_json()})
            except PayPalError as e:
                log.error("collections %s failed: %s", a.kind, e)
                report.append({"invoice_id": inv.id, "kind": a.kind, "error": str(e)})
    return report
