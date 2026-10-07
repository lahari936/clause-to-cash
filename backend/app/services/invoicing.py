import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import collections as collections_agent
from app.db.models import Clause, Contract, Invoice, Milestone, Party, PaymentTerms
from app.guard import Action
from app.money import dates
from app.paypal import invoices as pp_invoices
from app.paypal.client import PayPalError, get_client
from app.services.actions import Outcome, execute, ledger

PAID = ("PAID", "MARKED_AS_PAID")
log = logging.getLogger(__name__)


def client_party(db: Session, contract_id: int) -> Party:
    return db.scalars(
        select(Party).where(Party.contract_id == contract_id, Party.role == "client")
    ).one()


def _invoice_row(db: Session, key: str, **kw: Any) -> Invoice:
    """One row per business key (milestone / base invoice). The key is the PayPal-Request-Id, so
    a retry after any failure (even a timeout after PayPal accepted it) replays the same request
    instead of creating a second invoice. The unique key also stops concurrent duplicates."""
    inv = db.scalar(select(Invoice).where(Invoice.request_id == key).with_for_update())
    if inv is None:
        inv = Invoice(request_id=key, **kw)
        db.add(inv)
        db.flush()
    elif inv.status == "CANCELLED":
        # ponytail: re-issuing a cancelled invoice needs a versioned key (c2c-inv-m{id}-v2).
        raise PayPalError(
            409, "CANCELLED", "invoice was cancelled in PayPal; re-issue manually", None
        )
    elif inv.status == "FAILED":
        inv.status = "DRAFT"
        inv.due_date, inv.issued_on = kw["due_date"], kw["issued_on"]
    return inv


def _create_and_send(db: Session, inv: Invoice, draft: pp_invoices.InvoiceDraft) -> None:
    pp = get_client()
    try:
        if not inv.paypal_invoice_id:  # a retry reuses the draft created last time
            inv.paypal_invoice_id = pp_invoices.create_draft(pp, inv.request_id, draft)
        pp_invoices.send(pp, f"{inv.request_id}-send", inv.paypal_invoice_id)
    except PayPalError:
        inv.status = "FAILED"
        raise
    inv.status = "SENT"


def milestone_action(db: Session, m: Milestone, actor_source: str = "mandate") -> Action:
    c = db.get(Contract, m.contract_id)
    assert c and c.currency
    return Action(
        kind="milestone_invoice",
        contract_id=c.id,
        amount=m.amount,
        currency=c.currency,
        recipient=client_party(db, c.id).paypal_email or "",
        milestone_id=m.id,
        source="mandate" if actor_source == "mandate" else "free_text",
    )


def invoice_milestone(db: Session, m: Milestone, actor: str) -> Outcome:
    """Milestone accepted -> guard -> PayPal draft -> send. Amount/payee come from the mandate."""
    return execute(db, milestone_action(db, m), actor)


def issue_milestone_invoice(db: Session, a: Action) -> dict[str, Any]:
    assert a.milestone_id is not None
    m = db.get(Milestone, a.milestone_id)
    c = db.get(Contract, a.contract_id)
    terms = db.get(PaymentTerms, a.contract_id)
    assert m and c and terms
    cl = db.get(Clause, m.clause_id) if m.clause_id else None
    issued = dates.today()
    due = dates.due_date(issued, terms.net_days)
    inv = _invoice_row(
        db,
        f"c2c-inv-m{m.id}",
        contract_id=c.id,
        milestone_id=m.id,
        kind="milestone",
        amount=a.amount,
        due_date=due,
        issued_on=issued,
    )
    cite = f'Contract p.{cl.page}: "{cl.quote}"' if cl else ""
    note = (
        f"{c.title} - Milestone {m.seq}: {m.title}. Billed under the signed contract. {cite} "
        f"Payment due within {terms.net_days} days."
    )
    _create_and_send(
        db,
        inv,
        pp_invoices.InvoiceDraft(
            currency=a.currency,
            amount=a.amount,
            item_name=f"Milestone {m.seq}: {m.title}",
            item_description=m.deliverable,
            recipient_email=a.recipient,
            due_date=due,
            note=note,
            reference=f"C2C-{c.id}-M{m.seq}",
        ),
    )
    m.status = "invoiced"
    ledger(db, c.id, "invoice_sent", a.amount, f"invoice {inv.paypal_invoice_id} (M{m.seq})")
    return {"invoice_id": inv.id, "paypal_invoice_id": inv.paypal_invoice_id}


def issue_late_fee_invoice(db: Session, a: Action) -> dict[str, Any]:
    assert a.invoice_id is not None
    base = db.get(Invoice, a.invoice_id)
    c = db.get(Contract, a.contract_id)
    terms = db.get(PaymentTerms, a.contract_id)
    assert base and c and terms
    issued = dates.today()
    due = dates.due_date(issued, terms.net_days)
    inv = _invoice_row(
        db,
        f"c2c-inv-lf{base.id}",
        contract_id=c.id,
        base_invoice_id=base.id,
        kind="late_fee",
        amount=a.amount,
        due_date=due,
        issued_on=issued,
    )
    clause = _late_fee_clause(db, c.id)
    msg = collections_agent.write(
        "late fee",
        client_party(db, c.id).name,
        base.paypal_invoice_id or str(base.id),
        f"{base.amount} {c.currency}",
        str(base.due_date),
        clause,
        f"{a.amount} {c.currency}",
    )
    _create_and_send(
        db,
        inv,
        pp_invoices.InvoiceDraft(
            currency=a.currency,
            amount=a.amount,
            item_name="Contractual late fee",
            item_description=f"Late fee on {base.paypal_invoice_id}, per contract: {clause}",
            recipient_email=a.recipient,
            due_date=due,
            note=msg.body,
            reference=f"C2C-{c.id}-LF{base.id}",
        ),
    )
    ledger(db, c.id, "late_fee", a.amount, f"late fee invoice {inv.paypal_invoice_id}")
    return {"invoice_id": inv.id, "paypal_invoice_id": inv.paypal_invoice_id, "message": msg.body}


def _late_fee_clause(db: Session, contract_id: int) -> str:
    cl = db.scalar(
        select(Clause).where(Clause.contract_id == contract_id, Clause.kind == "late_fee")
    )
    return f'p.{cl.page}: "{cl.quote}"' if cl else "late fee clause"


def send_reminder(db: Session, a: Action) -> dict[str, Any]:
    assert a.invoice_id is not None
    inv = db.get(Invoice, a.invoice_id)
    c = db.get(Contract, a.contract_id)
    assert inv and c and inv.paypal_invoice_id
    msg = collections_agent.write(
        "reminder",
        client_party(db, c.id).name,
        inv.paypal_invoice_id,
        f"{inv.amount} {c.currency}",
        str(inv.due_date),
        _late_fee_clause(db, c.id),
    )
    rid = f"{inv.request_id}-remind-{dates.today().isoformat()}"
    pp_invoices.remind(get_client(), rid, inv.paypal_invoice_id, msg.subject, msg.body)
    inv.reminded_on = dates.today()
    return {"invoice_id": inv.id, "message": msg.body}


def mark_paid(db: Session, inv: Invoice, paid: Decimal | None) -> bool:
    """Idempotent: returns False if already processed. Triggers revenue-share payouts.
    The row lock serialises the webhook and the poll job so only one of them pays out."""
    db.refresh(inv, with_for_update=True)
    if inv.status == "PAID":
        return False
    inv.status = "PAID"
    inv.paid_amount = paid or inv.amount
    ledger(
        db, inv.contract_id, "payment_received", inv.paid_amount, f"invoice {inv.paypal_invoice_id}"
    )
    if inv.kind == "milestone" and inv.milestone_id:
        m = db.get(Milestone, inv.milestone_id)
        if m and m.status != "disputed":
            m.status = "paid"
        db.flush()
        from app.services import payouts

        try:
            payouts.pay_shares(db, inv)
        except PayPalError as e:  # payment stays recorded; failed payout rows are retryable
            log.error("payout batch failed: %s", e)
    return True


def sync_invoice(db: Session, inv: Invoice) -> str:
    """Pull truth from PayPal (used by webhooks and the poll job)."""
    if not inv.paypal_invoice_id:
        return inv.status
    st = pp_invoices.get_status(get_client(), inv.paypal_invoice_id)
    if st.status in PAID:
        mark_paid(db, inv, st.paid_amount)
    elif st.status == "CANCELLED":
        inv.status = "CANCELLED"
    return inv.status
