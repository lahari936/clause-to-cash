from sqlalchemy.orm import Session

from app.db.models import GuardEvent
from app.guard import Action
from app.services.actions import Outcome, execute


class ApprovalError(Exception):
    pass


def _pending(db: Session, event_id: int) -> GuardEvent:
    ev = db.get(GuardEvent, event_id)
    if ev is None or ev.decision != "NEEDS_APPROVAL" or ev.resolution != "pending":
        raise ApprovalError("no pending approval with that id")
    return ev


def approve(db: Session, event_id: int, by: str) -> Outcome:
    """Human approval re-runs the full guard (state may have changed) with approved_by set."""
    ev = _pending(db, event_id)
    ev.resolution = "approved"
    ev.approved_by = by
    return execute(
        db, Action.from_json(ev.payload_json), actor=f"{ev.actor} (approved)", approved_by=by
    )


def reject(db: Session, event_id: int, by: str) -> None:
    ev = _pending(db, event_id)
    ev.resolution = "rejected"
    ev.approved_by = by
