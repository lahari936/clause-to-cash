import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import dispute as dispute_agent
from app.db.models import (
    Clause,
    Contract,
    Delivery,
    Dispute,
    Invoice,
    LedgerEntry,
    Milestone,
    PaymentTerms,
)
from app.paypal import disputes as pp_disputes
from app.paypal.client import PayPalError, get_client
from app.services.actions import ledger

log = logging.getLogger(__name__)


def _match_invoice(db: Session, raw: dict[str, Any]) -> Invoice | None:
    for t in raw.get("disputed_transactions", []) or []:
        ref = t.get("invoice_number") or t.get("seller_transaction_id")
        if ref:
            inv = db.scalar(select(Invoice).where(Invoice.paypal_invoice_id == ref))
            if inv:
                return inv
    return db.scalar(
        select(Invoice)
        .where(Invoice.status == "PAID", Invoice.kind == "milestone")
        .order_by(Invoice.id.desc())
    )


def facts(db: Session, inv: Invoice, raw: dict[str, Any]) -> str:
    c = db.get(Contract, inv.contract_id)
    assert c
    lines = [f"Contract: {c.title} (id {c.id}), currency {c.currency}, total {c.total_amount}"]
    lines.append(
        f"Dispute reason: {raw.get('reason', 'unknown')}; buyer says: "
        f"{(raw.get('messages') or [{}])[0].get('content', 'n/a')}"
    )
    for cl in db.scalars(select(Clause).where(Clause.contract_id == c.id)):
        if cl.kind in ("milestone", "payment_terms", "late_fee", "dispute", "auto_accept", "total"):
            lines.append(f'Clause ({cl.kind}) page {cl.page}: "{cl.quote}"')
    terms = db.get(PaymentTerms, c.id)
    if terms:
        lines.append(f"Payment terms: net {terms.net_days} days")
    if inv.milestone_id:
        m = db.get(Milestone, inv.milestone_id)
        assert m
        lines.append(
            f"Disputed invoice {inv.paypal_invoice_id}: Milestone {m.seq} '{m.title}', "
            f"amount {inv.amount}, contracted {m.amount}, criteria: {m.acceptance_criteria}"
        )
        for d in db.scalars(select(Delivery).where(Delivery.milestone_id == m.id)):
            acc = d.acceptance_json or {}
            lines.append(
                f"Delivery {d.created_at:%Y-%m-%d} ({d.source}): {d.notes}; links {d.links}; "
                f"acceptance review: meets={acc.get('meets_criteria')} "
                f"summary={acc.get('summary_for_client')}"
            )
    for e in db.scalars(
        select(LedgerEntry).where(LedgerEntry.contract_id == c.id).order_by(LedgerEntry.ts)
    ):
        lines.append(f"Ledger {e.ts:%Y-%m-%d %H:%M}: {e.type} {e.amount} ({e.ref})")
    return "\n".join(lines)


def open_dispute(
    db: Session, paypal_dispute_id: str, raw: dict[str, Any], dry_run: bool
) -> Dispute:
    """Record a dispute and build its evidence pack. Idempotent on the PayPal dispute id."""
    existing = db.scalar(select(Dispute).where(Dispute.paypal_dispute_id == paypal_dispute_id))
    if existing:
        return existing
    inv = _match_invoice(db, raw)
    d = Dispute(
        paypal_dispute_id=paypal_dispute_id,
        invoice_id=inv.id if inv else None,
        contract_id=inv.contract_id if inv else None,
        reason=str(raw.get("reason", ""))[:100],
        status=str(raw.get("status", "OPEN")),
        dry_run=dry_run,
        raw_json=raw,
    )
    db.add(d)
    if inv:
        if inv.milestone_id and (m := db.get(Milestone, inv.milestone_id)):
            m.status = "disputed"
        ledger(db, inv.contract_id, "dispute", inv.amount, f"dispute {paypal_dispute_id}")
        pack = dispute_agent.build(facts(db, inv, raw))
        d.evidence_md = pack.evidence_markdown
        d.proposed_response = pack.proposed_response
        d.evidence_pdf = dispute_agent.to_pdf(pack.evidence_markdown)
        d.evidence_pack_key = f"db:dispute:{paypal_dispute_id}"
    db.flush()
    return d


def submit(db: Session, d: Dispute, by: str) -> str:
    """Human-approved submission. Dry-run disputes never call PayPal."""
    if d.submitted_at:
        return "already submitted"
    if not d.evidence_pdf:
        raise ValueError("no evidence pack")
    if d.dry_run:
        d.status = "EVIDENCE_READY (dry run)"
    else:
        try:
            pp_disputes.provide_evidence(
                get_client(),
                f"c2c-dispute-{d.id}",
                d.paypal_dispute_id,
                d.evidence_pdf,
                d.proposed_response or "",
            )
            d.status = "EVIDENCE_SUBMITTED"
        except PayPalError as e:
            log.warning("provide-evidence failed, marking dry run: %s", e)
            d.dry_run = True
            d.status = f"EVIDENCE_READY (dry run: {e.name})"
    d.submitted_at = datetime.now(UTC)
    return f"{d.status} by {by}"
