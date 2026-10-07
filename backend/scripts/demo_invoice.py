"""Live sandbox check for task 2.4: deliver + accept milestone 1 of the demo contract, which
creates and sends a real PayPal sandbox invoice through the guard. Prints the invoice id."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.models import Contract, Invoice, Milestone  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import milestones  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        c = db.scalar(
            select(Contract).where(Contract.status == "approved").order_by(Contract.id.desc())
        )
        if not c:
            sys.exit("run scripts/seed_demo.py first")
        m = db.scalars(
            select(Milestone)
            .where(Milestone.contract_id == c.id, Milestone.status.in_(("planned", "delivered")))
            .order_by(Milestone.seq)
        ).first()
        if not m:
            sys.exit("no milestone left to invoice")
        if m.status == "planned":
            milestones.deliver(
                db,
                m,
                "Figma design system shared covering home, product and checkout pages.",
                ["https://figma.com/file/demo"],
            )
        out = milestones.accept(db, m, "demo_invoice.py")
        db.commit()
        print(out.to_json())
        if out.decision.allowed:
            inv = db.scalars(select(Invoice).where(Invoice.milestone_id == m.id)).one()
            print(f"sandbox invoice sent: {inv.paypal_invoice_id} (local id {inv.id})")


if __name__ == "__main__":
    main()
