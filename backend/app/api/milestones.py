from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import row
from app.db.models import Delivery, Milestone
from app.db.session import get_db
from app.paypal.client import PayPalError
from app.services import milestones as svc

router = APIRouter(prefix="/milestones", tags=["milestones"])


def get_milestone(db: Session, milestone_id: int) -> Milestone:
    m = db.get(Milestone, milestone_id)
    if m is None:
        raise HTTPException(404, "milestone not found")
    return m


class DeliveryIn(BaseModel):
    notes: str = Field("", max_length=10000)
    links: list[str] = Field(default_factory=list, max_length=20)


@router.post("/{milestone_id}/deliveries", status_code=201)
def deliver(milestone_id: int, body: DeliveryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = get_milestone(db, milestone_id)
    try:
        d = svc.deliver(db, m, body.notes, body.links)
    except svc.MilestoneError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return row(d)


@router.get("/{milestone_id}/deliveries")
def deliveries(milestone_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(Delivery).where(Delivery.milestone_id == milestone_id).order_by(Delivery.id.desc())
    return [row(d) for d in db.scalars(q)]


class AcceptIn(BaseModel):
    by: str


@router.post("/{milestone_id}/accept")
def accept(milestone_id: int, body: AcceptIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = get_milestone(db, milestone_id)
    try:
        out = svc.accept(db, m, body.by)
    except svc.MilestoneError as e:
        raise HTTPException(409, str(e)) from e
    except PayPalError as e:
        db.commit()  # keep the guard event + FAILED invoice row
        raise HTTPException(502, str(e)) from e
    db.commit()
    return out.to_json()
