"""Background jobs: poll invoice/payout status (webhook backup), auto-accept, daily collections."""

import logging
from collections.abc import Callable
from typing import Any

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


def _each(db: Session, items: list[Any], fn: Callable[[Any], object]) -> None:
    """Commit per item so one bad invoice/batch doesn't roll back the others."""
    for it in items:
        try:
            fn(it)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("poll item %s failed", it)


def poll(db: Session) -> None:
    sent = list(db.scalars(select(Invoice).where(Invoice.status == "SENT")))
    _each(db, sent, lambda inv: invoicing.sync_invoice(db, inv))
    batches = db.scalars(
        select(Payout.paypal_batch_id).where(Payout.status.in_(("SENT", "UNCLAIMED"))).distinct()
    ).all()
    _each(db, [b for b in batches if b], lambda b: payouts.sync_batch(db, b))
    payouts.retry_failed(db)


def start() -> BackgroundScheduler:
    s = BackgroundScheduler(timezone="UTC")
    s.add_job(_job(poll), "interval", seconds=60, id="poll", max_instances=1)
    s.add_job(_job(milestones.auto_accept_due), "interval", minutes=10, id="auto_accept")
    s.add_job(_job(collections.run), "cron", hour=9, id="collections")
    s.start()
    return s
