"""Single entry point for money actions: guard.check() first, execute only on ALLOW."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app import guard
from app.db.models import LedgerEntry
from app.guard import Action, Decision


@dataclass
class Outcome:
    decision: Decision
    result: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        d = self.decision
        return {
            "decision": d.decision,
            "rule_ids": d.rule_ids,
            "reason": d.reason,
            "guard_event_id": d.event_id,
            **self.result,
        }


def ledger(db: Session, contract_id: int, type_: str, amount: Any, ref: str) -> None:
    db.add(LedgerEntry(contract_id=contract_id, type=type_, amount=amount, ref=ref))


def execute(db: Session, action: Action, actor: str, approved_by: str | None = None) -> Outcome:
    from app.services import invoicing, payouts

    decision = guard.check(db, action, actor, approved_by)
    if not decision.allowed:
        return Outcome(decision)
    handlers = {
        "milestone_invoice": invoicing.issue_milestone_invoice,
        "late_fee_invoice": invoicing.issue_late_fee_invoice,
        "remind": invoicing.send_reminder,
        "payout": payouts.send_one,
    }
    return Outcome(decision, handlers[action.kind](db, action))
