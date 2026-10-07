"""Task 2.5 check: wait up to 2 minutes for a PayPal invoice to be PAID in our DB.
Usage: python scripts/assert_paid.py <paypal_invoice_id>"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.models import Invoice, LedgerEntry  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import invoicing  # noqa: E402


def main(pp_id: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            inv = db.scalar(select(Invoice).where(Invoice.paypal_invoice_id == pp_id))
            if inv is None:
                sys.exit(f"unknown invoice {pp_id}")
            if inv.status != "PAID":
                invoicing.sync_invoice(db, inv)  # same path as the webhook/poll job
                db.commit()
            if inv.status == "PAID":
                types = db.scalars(
                    select(LedgerEntry.type).where(LedgerEntry.contract_id == inv.contract_id)
                ).all()
                print(f"PAID: {pp_id} amount {inv.paid_amount}; ledger {types}")
                return
        time.sleep(10)
    sys.exit(f"{pp_id} not PAID within 2 minutes")


if __name__ == "__main__":
    main(sys.argv[1])
