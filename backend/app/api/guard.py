from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import row
from app.db.models import GuardEvent
from app.db.session import get_db
from app.paypal.client import PayPalError
from app.services import approvals

router = APIRouter(prefix="/guard", tags=["guard"])


@router.get("/events")
def events(
    contract_id: int | None = None, pending: bool = False, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    q = select(GuardEvent)
    if contract_id:
        q = q.where(GuardEvent.contract_id == contract_id)
    if pending:
        q = q.where(GuardEvent.resolution == "pending")
    return [row(e) for e in db.scalars(q.order_by(GuardEvent.id.desc()).limit(500))]


class By(BaseModel):
    by: str


@router.post("/events/{event_id}/approve")
def approve(event_id: int, body: By, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        out = approvals.approve(db, event_id, body.by)
    except approvals.ApprovalError as e:
        raise HTTPException(409, str(e)) from e
    except PayPalError as e:
        db.commit()
        raise HTTPException(502, str(e)) from e
    db.commit()
    return out.to_json()


@router.post("/events/{event_id}/reject")
def reject(event_id: int, body: By, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        approvals.reject(db, event_id, body.by)
    except approvals.ApprovalError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return {"status": "rejected"}
