"""guard.check(): load mandate + state from Postgres, run rules, record a guard_event."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Contract, GuardEvent, Invoice, Mandate, Milestone, Party, Payout
from app.guard.mandate import Action, InvoiceView, MandateView, MilestoneView, PartyView, State
from app.guard.rules import RuleResult, evaluate
from app.money import dates
from app.money.late_fee import LateFeeTerms

DecisionKind = Literal["ALLOW", "DENY", "NEEDS_APPROVAL"]
DEAD = ("CANCELLED", "FAILED")


@dataclass(frozen=True)
class Decision:
    decision: DecisionKind
    rule_ids: list[str]
    reason: str
    event_id: int

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"


def load_mandate(db: Session, contract_id: int) -> MandateView | None:
    mandate = db.scalar(select(Mandate).where(Mandate.contract_id == contract_id))
    contract = db.get(Contract, contract_id)
    if mandate is None or contract is None:
        return None
    r = mandate.rules_json
    lf = r["late_fee"]
    parties = db.scalars(select(Party).where(Party.contract_id == contract_id)).all()
    milestones = db.scalars(select(Milestone).where(Milestone.contract_id == contract_id)).all()
    return MandateView(
        contract_status=contract.status,
        currency=r["currency"],
        total=Decimal(r["total_amount"]),
        client_email=r["client_paypal_email"],
        approval_threshold=mandate.approval_threshold,
        late_fee=LateFeeTerms(
            lf["type"],
            Decimal(lf["value"]),
            int(lf["grace_days"]),
            Decimal(lf["cap"]) if lf.get("cap") is not None else None,
        ),
        parties={p.id: PartyView(p.role, p.paypal_email or "", p.share_pct) for p in parties},
        milestones={m.id: MilestoneView(m.amount, m.status) for m in milestones},
    )


def _executed(db: Session, a: Action) -> bool:
    if a.kind == "milestone_invoice":
        q = select(Invoice.id).where(
            Invoice.kind == "milestone",
            Invoice.milestone_id == a.milestone_id,
            Invoice.status.not_in(DEAD),
        )
    elif a.kind == "late_fee_invoice":
        q = select(Invoice.id).where(
            Invoice.kind == "late_fee",
            Invoice.base_invoice_id == a.invoice_id,
            Invoice.status.not_in(DEAD),
        )
    elif a.kind == "payout":
        q = select(Payout.id).where(
            Payout.invoice_id == a.invoice_id,
            Payout.party_id == a.party_id,
            Payout.status.not_in(DEAD),
        )
    else:  # remind: at most once per day
        inv = db.get(Invoice, a.invoice_id) if a.invoice_id else None
        return inv is not None and inv.reminded_on == dates.today()
    return db.scalar(q.limit(1)) is not None


def load_state(db: Session, a: Action, approved_by: str | None) -> State:
    invoiced = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.contract_id == a.contract_id,
            Invoice.kind == "milestone",
            Invoice.status.not_in(DEAD),
        )
    )
    inv = db.get(Invoice, a.invoice_id) if a.invoice_id is not None else None
    return State(
        today=dates.today(),
        invoiced_total=Decimal(invoiced or 0),
        already_executed=_executed(db, a),
        invoice=InvoiceView(inv.kind, inv.amount, inv.status, inv.due_date, inv.paid_amount)
        if inv and inv.contract_id == a.contract_id
        else None,
        approved_by=approved_by,
    )


def decide(results: list[RuleResult]) -> tuple[DecisionKind, list[RuleResult]]:
    denied = [r for r in results if r.outcome == "deny"]
    if denied:
        return "DENY", denied
    pending = [r for r in results if r.outcome == "approval"]
    if pending:
        return "NEEDS_APPROVAL", pending
    return "ALLOW", []


def check(db: Session, action: Action, actor: str, approved_by: str | None = None) -> Decision:
    """Evaluate an action against the mandate. Always writes a guard_event (caller commits)."""
    results = evaluate(
        action, load_mandate(db, action.contract_id), load_state(db, action, approved_by)
    )
    kind, why = decide(results)
    reason = "; ".join(f"{r.rule_id}: {r.reason}" for r in why) or "all rules passed"
    ev = GuardEvent(
        contract_id=action.contract_id,
        actor=actor,
        action=action.kind,
        payload_json=action.to_json(),
        decision=kind,
        rule_ids=[r.rule_id for r in why] or [r.rule_id for r in results],
        reason=reason,
        approved_by=approved_by,
        resolution="pending" if kind == "NEEDS_APPROVAL" else None,
    )
    db.add(ev)
    db.flush()
    return Decision(kind, list(ev.rule_ids), reason, ev.id)
