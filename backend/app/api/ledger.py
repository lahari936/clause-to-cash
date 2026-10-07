from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import row
from app.config import get_settings
from app.db.models import Contract, Invoice, LedgerEntry, Party, Payout
from app.db.session import get_db
from app.money import dates
from app.paypal.client import PayPalError
from app.services import collections, invoicing

router = APIRouter(tags=["ledger"])


@router.get("/ledger")
def ledger(contract_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(LedgerEntry, Contract.title, Contract.currency).join(Contract)
    if contract_id:
        q = q.where(LedgerEntry.contract_id == contract_id)
    return [
        row(e, contract=t, currency=cur) for e, t, cur in db.execute(q.order_by(LedgerEntry.ts))
    ]


@router.get("/invoices")
def invoices(contract_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(Invoice)
    if contract_id:
        q = q.where(Invoice.contract_id == contract_id)
    return [row(i) for i in db.scalars(q.order_by(Invoice.id))]


@router.post("/invoices/{invoice_id}/sync")
def sync(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404, "invoice not found")
    try:
        invoicing.sync_invoice(db, inv)
    except PayPalError as e:
        raise HTTPException(502, str(e)) from e
    db.commit()
    return row(inv)


@router.get("/payouts")
def payouts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(Payout, Party.name, Party.paypal_email).join(Party, Payout.party_id == Party.id)
    return [row(p, party=n, email=e) for p, n, e in db.execute(q.order_by(Payout.id))]


@router.post("/collections/run")
def run_collections(db: Session = Depends(get_db)) -> dict[str, Any]:
    report = collections.run(db, actor="collections (run now)")
    db.commit()
    return {"today": dates.today().isoformat(), "actions": report}


class Clock(BaseModel):
    today: date | None


@router.get("/demo/clock")
def get_clock() -> dict[str, str]:
    return {"today": dates.today().isoformat()}


@router.post("/demo/clock")
def set_clock(body: Clock) -> dict[str, str]:
    if not get_settings().allow_demo_clock:
        raise HTTPException(403, "demo clock disabled (ALLOW_DEMO_CLOCK=false)")
    dates.set_today(body.today)
    return {"today": dates.today().isoformat()}
