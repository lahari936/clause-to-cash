"""Plain data the guard rules read. Built from the frozen mandate snapshot + live DB state."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from app.money.late_fee import LateFeeTerms

ActionKind = Literal["milestone_invoice", "late_fee_invoice", "payout", "remind"]
Source = Literal["mandate", "free_text"]


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    contract_id: int
    amount: Decimal
    currency: str
    recipient: str
    milestone_id: int | None = None
    invoice_id: int | None = None
    party_id: int | None = None
    source: Source = "mandate"  # free_text = requested by a chat/LLM instruction
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "contract_id": self.contract_id,
            "amount": str(self.amount),
            "currency": self.currency,
            "recipient": self.recipient,
            "milestone_id": self.milestone_id,
            "invoice_id": self.invoice_id,
            "party_id": self.party_id,
            "source": self.source,
            "note": self.note,
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Action":
        return Action(**{**d, "amount": Decimal(d["amount"])})


@dataclass(frozen=True)
class PartyView:
    role: str
    email: str
    share_pct: Decimal | None


@dataclass(frozen=True)
class MilestoneView:
    amount: Decimal
    status: str


@dataclass(frozen=True)
class MandateView:
    contract_status: str
    currency: str
    total: Decimal
    client_email: str
    approval_threshold: Decimal
    late_fee: LateFeeTerms
    parties: dict[int, PartyView] = field(default_factory=dict)
    milestones: dict[int, MilestoneView] = field(default_factory=dict)


@dataclass(frozen=True)
class InvoiceView:
    kind: str
    amount: Decimal
    status: str
    due_date: date | None
    paid_amount: Decimal | None


@dataclass(frozen=True)
class State:
    today: date
    invoiced_total: Decimal  # milestone invoices already issued (not cancelled)
    already_executed: bool  # same (kind, milestone/invoice, party) already done
    invoice: InvoiceView | None = None  # the invoice an action refers to
    approved_by: str | None = None
