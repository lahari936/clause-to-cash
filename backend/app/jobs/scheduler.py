"""Background jobs: poll invoice/payout status (webhook backup), auto-accept, daily collections."""

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Invoice, Payout
from app.db.session import SessionLocal
from app.services import collections, invoicing, milestones, payouts

log = logging.getLogger(__name__)


def _job(fn: Callable[[Session], object]) -> Callable[[], None]:
    def run() -> None:
        with SessionLocal() as db:
            try:
                fn(db)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("job %s failed", fn.__name__)

    return run


def poll(db: Session) -> None:
    for inv in db.scalars(select(Invoice).where(Invoice.status == "SENT")).all():
        invoicing.sync_invoice(db, inv)
    batches = db.scalars(
        select(Payout.paypal_batch_id).where(Payout.status.in_(("SENT", "UNCLAIMED"))).distinct()
    ).all()
    for b in batches:
        if b:
            payouts.sync_batch(db, b)


def start() -> BackgroundScheduler:
    s = BackgroundScheduler(timezone="UTC")
    s.add_job(_job(poll), "interval", seconds=60, id="poll", max_instances=1)
    s.add_job(_job(milestones.auto_accept_due), "interval", minutes=10, id="auto_accept")
    s.add_job(_job(collections.run), "cron", hour=9, id="collections")
    s.start()
    return s
