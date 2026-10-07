from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Cited(BaseModel):
    page: int = Field(description="1-based page number the quote is on")
    quote: str = Field(max_length=300, description="verbatim text copied from that page")
    confidence: float = Field(ge=0, le=1)


class PartyX(BaseModel):
    role: Literal["client", "agency", "subcontractor"]
    name: str
    email: str | None
    share_pct: Decimal | None = Field(description="revenue share % for subcontractors, else null")
    cite: Cited


class MilestoneX(BaseModel):
    seq: int
    title: str
    deliverable: str
    acceptance_criteria: list[str]
    amount: Decimal
    due_date: date | None
    cite: Cited


class LateFeeX(BaseModel):
    type: Literal["pct_monthly", "pct_flat", "fixed", "none"]
    value: Decimal = Field(description="percent for pct_* types, amount for fixed, 0 for none")
    grace_days: int
    cap: Decimal | None = Field(description="maximum total late fee amount, null if no cap")
    cite: Cited | None


class ContractExtraction(BaseModel):
    title: str
    currency: str = Field(description="ISO 4217 code")
    total_amount: Decimal
    total_cite: Cited
    parties: list[PartyX]
    milestones: list[MilestoneX]
    net_days: int
    net_days_cite: Cited
    late_fee: LateFeeX
    deposit_amount: Decimal | None
    auto_accept_days: int | None = Field(description="'deemed accepted after N days', else null")
    auto_accept_cite: Cited | None
    dispute_clause: Cited | None
