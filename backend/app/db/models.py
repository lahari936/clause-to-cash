"""Tables from PLAN.md section 4. Money is NUMERIC(12,2), never float."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Numeric(12, 2)


class Base(DeclarativeBase):
    pass


def _enum(name: str, *values: str) -> Enum:
    return Enum(*values, name=name)


def _id() -> Mapped[int]:
    return mapped_column(Integer, primary_key=True)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = _id()
    title: Mapped[str] = mapped_column(String(300))
    file_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        _enum("contract_status", "uploaded", "extracted", "review", "approved", "archived"),
        default="uploaded",
    )
    currency: Mapped[str | None] = mapped_column(String(3))
    total_amount: Mapped[Decimal | None] = mapped_column(Money)
    created_at: Mapped[datetime] = _now()
    # Render's free disk is ephemeral, so the PDF and its page texts live in Postgres.
    pdf: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    pages_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    extraction_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Party(Base):
    __tablename__ = "parties"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(_enum("party_role", "client", "agency", "subcontractor"))
    name: Mapped[str] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(320))
    paypal_email: Mapped[str | None] = mapped_column(String(320))
    share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))


class Clause(Base):
    __tablename__ = "clauses"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(50))
    page: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(String(300))
    section_ref: Mapped[str | None] = mapped_column(String(50))


class Milestone(Base):
    __tablename__ = "milestones"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    deliverable: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    amount: Mapped[Decimal] = mapped_column(Money)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        _enum(
            "milestone_status", "planned", "delivered", "accepted", "invoiced", "paid", "disputed"
        ),
        default="planned",
    )
    clause_id: Mapped[int | None] = mapped_column(ForeignKey("clauses.id"))


class PaymentTerms(Base):
    __tablename__ = "payment_terms"
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True
    )
    net_days: Mapped[int] = mapped_column(Integer)
    late_fee_type: Mapped[str] = mapped_column(
        _enum("late_fee_type", "pct_monthly", "pct_flat", "fixed", "none")
    )
    late_fee_value: Mapped[Decimal] = mapped_column(Money)
    grace_days: Mapped[int] = mapped_column(Integer, default=0)
    late_fee_cap: Mapped[Decimal | None] = mapped_column(Money)
    deposit_amount: Mapped[Decimal | None] = mapped_column(Money)
    clause_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)


class ExtractionField(Base):
    __tablename__ = "extraction_fields"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(200))
    value_json: Mapped[Any] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)  # model score 0..1, not money
    clause_id: Mapped[int | None] = mapped_column(ForeignKey("clauses.id"))
    checker_verdict: Mapped[str | None] = mapped_column(
        _enum("checker_verdict", "ok", "wrong", "unsupported")
    )
    checker_reason: Mapped[str | None] = mapped_column(Text)
    user_override_json: Mapped[Any | None] = mapped_column(JSON)


class Mandate(Base):
    __tablename__ = "mandates"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str] = mapped_column(String(200))
    approved_at: Mapped[datetime] = _now()
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    approval_threshold: Mapped[Decimal] = mapped_column(Money)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"))
    base_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    kind: Mapped[str] = mapped_column(_enum("invoice_kind", "milestone", "late_fee"))
    paypal_invoice_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    request_id: Mapped[str] = mapped_column(String(100), unique=True)
    issued_on: Mapped[date | None] = mapped_column(Date)
    reminded_on: Mapped[date | None] = mapped_column(Date)
    paid_amount: Mapped[Decimal | None] = mapped_column(Money)


class Payout(Base):
    __tablename__ = "payouts"
    id: Mapped[int] = _id()
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    paypal_batch_id: Mapped[str | None] = mapped_column(String(64))
    paypal_item_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    request_id: Mapped[str] = mapped_column(String(100), unique=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    ts: Mapped[datetime] = _now()
    type: Mapped[str] = mapped_column(
        _enum(
            "ledger_type",
            "invoice_sent",
            "payment_received",
            "late_fee",
            "payout_sent",
            "payout_done",
            "refund",
            "dispute",
        )
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    ref: Mapped[str | None] = mapped_column(String(200))


class GuardEvent(Base):
    __tablename__ = "guard_events"
    id: Mapped[int] = _id()
    ts: Mapped[datetime] = _now()
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(
        _enum("guard_decision", "ALLOW", "DENY", "NEEDS_APPROVAL")
    )
    rule_ids: Mapped[list[str]] = mapped_column(ARRAY(String(10)), default=list)
    reason: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    # pending | approved | rejected (only for NEEDS_APPROVAL rows)
    resolution: Mapped[str | None] = mapped_column(String(20))


class Dispute(Base):
    __tablename__ = "disputes"
    id: Mapped[int] = _id()
    paypal_dispute_id: Mapped[str] = mapped_column(String(64), unique=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    reason: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    evidence_pack_key: Mapped[str | None] = mapped_column(String(500))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_md: Mapped[str | None] = mapped_column(Text)
    evidence_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    proposed_response: Mapped[str | None] = mapped_column(Text)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    type: Mapped[str] = mapped_column(String(100))
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Boolean)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = _id()
    milestone_id: Mapped[int] = mapped_column(ForeignKey("milestones.id"))
    notes: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    source: Mapped[str] = mapped_column(_enum("delivery_source", "manual", "github"))
    acceptance_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = _now()
