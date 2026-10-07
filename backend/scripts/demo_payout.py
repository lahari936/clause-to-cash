"""Task 3.3 check: show (and refresh from PayPal) the revenue-share payouts of paid invoices."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.models import Invoice, LedgerEntry, Party, Payout  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import payouts  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        paid = db.scalars(
            select(Invoice).where(Invoice.status == "PAID", Invoice.kind == "milestone")
        ).all()
        if not paid:
            sys.exit("no PAID milestone invoice yet: pay one as the client sandbox account first")
        for inv in paid:
            if not db.scalar(select(Payout.id).where(Payout.invoice_id == inv.id)):
                payouts.pay_shares(db, inv, actor="demo_payout.py")
        for b in set(db.scalars(select(Payout.paypal_batch_id)).all()):
            if b:
                payouts.sync_batch(db, b)
        db.commit()
        for p, name, email in db.execute(
            select(Payout, Party.name, Party.paypal_email).join(Party)
        ):
            print(f"{name} <{email}>: {p.amount} status={p.status} batch={p.paypal_batch_id}")
        done = db.scalars(select(LedgerEntry).where(LedgerEntry.type == "payout_done")).all()
        print(f"ledger payout_done entries: {len(done)}")


if __name__ == "__main__":
    main()
