import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import guard
from app.db.models import Contract, Invoice, Party, Payout
from app.guard import Action
from app.money import splits
from app.paypal import payouts as pp_payouts
from app.paypal.client import PayPalError, get_client
from app.services.actions import Outcome, ledger

log = logging.getLogger(__name__)


def share_actions(db: Session, inv: Invoice) -> list[Action]:
    c = db.get(Contract, inv.contract_id)
    assert c and c.currency
    subs = db.scalars(
        select(Party).where(Party.contract_id == c.id, Party.role == "subcontractor")
    ).all()
    paid = inv.paid_amount or inv.amount
    return [
        Action(
            kind="payout",
            contract_id=c.id,
            amount=splits.share(paid, p.share_pct),
            currency=c.currency,
            recipient=p.paypal_email or "",
            invoice_id=inv.id,
            party_id=p.id,
        )
        for p in subs
        if p.share_pct
    ]


def _send(db: Session, actions: list[Action]) -> list[Payout]:
    """One PayPal batch for all already-ALLOWed payout actions."""
    if not actions:
        return []
    rows: list[Payout] = []
    sent: list[Action] = []
    for a in actions:
        assert a.invoice_id is not None and a.party_id is not None
        # Key = (invoice, party): one row ever per share; a FAILED row is reused on retry and the
        # unique key makes a concurrent duplicate insert fail instead of paying twice.
        key = f"c2c-po-inv{a.invoice_id}-p{a.party_id}"
        p = db.scalar(select(Payout).where(Payout.request_id == key).with_for_update())
        if p is None:
            p = Payout(
                invoice_id=a.invoice_id, party_id=a.party_id, amount=a.amount, request_id=key
            )
            db.add(p)
            db.flush()
        elif p.status != "FAILED":  # another processor sent it while we waited for the lock
            continue
        p.status = "PENDING"
        rows.append(p)
        sent.append(a)
    if not rows:
        return []
    actions = sent
    inv = db.get(Invoice, actions[0].invoice_id)
    assert inv
    # Same set of shares -> same batch id -> PayPal replays instead of paying again.
    parties = "-".join(str(a.party_id) for a in sorted(actions, key=lambda a: a.party_id or 0))
    batch_id = f"c2c-batch-inv{inv.id}-p{parties}"
    items = [
        pp_payouts.PayoutItem(
            r.request_id,
            a.recipient,
            a.amount,
            a.currency,
            f"Revenue share for invoice {inv.paypal_invoice_id}",
        )
        for r, a in zip(rows, actions, strict=True)
    ]
    try:
        pp_batch = pp_payouts.create_batch(get_client(), batch_id, "You have a payout", items)
    except PayPalError:
        for r in rows:
            r.status = "FAILED"
        raise
    for r, a in zip(rows, actions, strict=True):
        r.paypal_batch_id = pp_batch
        r.status = "SENT"
        ledger(
            db, a.contract_id, "payout_sent", a.amount, f"payout {r.request_id} batch {pp_batch}"
        )
    return rows


def send_one(db: Session, a: Action) -> dict[str, Any]:
    rows = _send(db, [a])
    return {"payout_id": rows[0].id, "paypal_batch_id": rows[0].paypal_batch_id}


def pay_shares(
    db: Session, inv: Invoice, actor: str = "payouts", only_parties: set[int] | None = None
) -> list[Outcome]:
    """On PAID: every share goes through the guard; ALLOWed ones go out as one batch."""
    outcomes, allowed = [], []
    for a in share_actions(db, inv):
        if only_parties is not None and a.party_id not in only_parties:
            continue
        d = guard.check(db, a, actor)
        outcomes.append(Outcome(d))
        if d.allowed:
            allowed.append(a)
    rows = _send(db, allowed)
    for o, r in zip([o for o in outcomes if o.decision.allowed], rows, strict=True):
        o.result = {"payout_id": r.id, "paypal_batch_id": r.paypal_batch_id}
    return outcomes


def retry_failed(db: Session) -> None:
    """Poll-job hook: re-send shares whose payout FAILED (same keys, so never double-paid)."""
    failed = db.execute(
        select(Payout.invoice_id, Payout.party_id).where(Payout.status == "FAILED")
    ).all()
    by_inv: dict[int, set[int]] = {}
    for inv_id, party_id in failed:
        by_inv.setdefault(inv_id, set()).add(party_id)
    for inv_id, parties in by_inv.items():
        inv = db.get(Invoice, inv_id)
        if inv and inv.status == "PAID":
            try:
                pay_shares(db, inv, actor="payouts (retry)", only_parties=parties)
            except PayPalError as e:
                # One automatic retry only. A second failure may mean PayPal already took the
                # batch (a reused sender_batch_id is rejected), so a human reconciles it.
                log.error("payout retry failed, needs review: %s", e)
                for p in db.scalars(
                    select(Payout).where(Payout.invoice_id == inv_id, Payout.status == "FAILED")
                ):
                    p.status = "NEEDS_REVIEW"


def sync_batch(db: Session, batch_id: str) -> None:
    status, items = pp_payouts.get_batch(get_client(), batch_id)
    by_req = {i.sender_item_id: i for i in items}
    for p in db.scalars(select(Payout).where(Payout.paypal_batch_id == batch_id)):
        it = by_req.get(p.request_id)
        if not it:
            continue
        p.paypal_item_id = it.payout_item_id
        new = {
            "SUCCESS": "SUCCESS",
            "FAILED": "FAILED",
            "RETURNED": "RETURNED",  # never auto-retried; the agency follows up
            "BLOCKED": "RETURNED",
            "UNCLAIMED": "UNCLAIMED",
        }.get(it.status, p.status)
        if new == "SUCCESS" and p.status != "SUCCESS":
            inv = db.get(Invoice, p.invoice_id)
            assert inv
            ledger(db, inv.contract_id, "payout_done", p.amount, f"payout {p.request_id}")
        p.status = new
