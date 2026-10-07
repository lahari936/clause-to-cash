import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import acceptance
from app.db.models import Contract, Delivery, Mandate, Milestone
from app.money import dates
from app.services import invoicing
from app.services.actions import Outcome

log = logging.getLogger(__name__)


class MilestoneError(Exception):
    pass


def deliver(
    db: Session, m: Milestone, notes: str, links: list[str], source: str = "manual"
) -> Delivery:
    c = db.get(Contract, m.contract_id)
    if not c or c.status != "approved":
        raise MilestoneError("contract has no approved mandate")
    if m.status not in ("planned", "delivered"):
        raise MilestoneError(f"milestone is already {m.status}")
    try:
        review = acceptance.review(m.title, m.acceptance_criteria, notes, links).model_dump()
    except Exception as e:  # agent advisory only; delivery is still recorded
        log.warning("acceptance agent failed: %s", e)
        review = {
            "meets_criteria": None,
            "gaps": ["acceptance agent unavailable"],
            "summary_for_client": notes,
        }
    d = Delivery(milestone_id=m.id, notes=notes, links=links, source=source, acceptance_json=review)
    db.add(d)
    m.status = "delivered"
    db.flush()
    return d


def accept(db: Session, m: Milestone, by: str) -> Outcome:
    """Agency confirms acceptance -> milestone accepted -> guarded invoice."""
    if m.status not in ("delivered", "accepted"):
        raise MilestoneError(f"milestone is {m.status}; deliver it first")
    m.status = "accepted"
    db.flush()
    return invoicing.invoice_milestone(db, m, actor=by)


def auto_accept_due(db: Session) -> list[int]:
    """'Deemed accepted after N days' clauses: accept delivered milestones whose window passed."""
    done = []
    for m in db.scalars(select(Milestone).where(Milestone.status == "delivered")).all():
        mandate = db.scalar(select(Mandate).where(Mandate.contract_id == m.contract_id))
        n = mandate.rules_json.get("auto_accept_days") if mandate else None
        last = db.scalar(
            select(Delivery).where(Delivery.milestone_id == m.id).order_by(Delivery.id.desc())
        )
        if n and last and dates.today() >= last.created_at.date() + timedelta(days=int(n)):
            accept(db, m, by=f"auto-accept ({n} days, contract clause)")
            done.append(m.id)
    return done
