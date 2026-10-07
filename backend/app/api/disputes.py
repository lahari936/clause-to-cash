import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.api.serialize import row
from app.db.models import Dispute, Invoice
from app.db.session import get_db
from app.services import disputes as svc

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.get("")
def list_disputes(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [row(d) for d in db.scalars(select(Dispute).order_by(Dispute.id.desc()))]


@router.get("/{dispute_id}/pdf")
def pdf(dispute_id: int, db: Session = Depends(get_db)) -> Response:
    d = db.scalar(
        select(Dispute).where(Dispute.id == dispute_id).options(undefer(Dispute.evidence_pdf))
    )
    if d is None or not d.evidence_pdf:
        raise HTTPException(404, "no evidence pack")
    return Response(d.evidence_pdf, media_type="application/pdf")


class DemoDispute(BaseModel):
    invoice_id: int
    message: str = "I was charged but the work was not delivered as agreed."


@router.post("/demo", status_code=201)
def demo(body: DemoDispute, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Sandbox disputes on invoice payments are hard to trigger; this opens a dry-run dispute."""
    inv = db.get(Invoice, body.invoice_id)
    if inv is None or inv.status != "PAID":
        raise HTTPException(409, "pick a PAID invoice")
    raw = {
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "OPEN",
        "disputed_transactions": [{"invoice_number": inv.paypal_invoice_id}],
        "messages": [{"posted_by": "BUYER", "content": body.message}],
    }
    d = svc.open_dispute(db, f"DRYRUN-{uuid.uuid4().hex[:10].upper()}", raw, dry_run=True)
    db.commit()
    return row(d)


class By(BaseModel):
    by: str


@router.post("/{dispute_id}/submit")
def submit(dispute_id: int, body: By, db: Session = Depends(get_db)) -> dict[str, str]:
    d = db.scalar(
        select(Dispute).where(Dispute.id == dispute_id).options(undefer(Dispute.evidence_pdf))
    )
    if d is None:
        raise HTTPException(404, "dispute not found")
    try:
        status = svc.submit(db, d, body.by)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return {"status": status}
