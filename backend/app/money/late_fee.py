"""Contract-correct late fee. Deterministic; the LLM may explain it, never compute it."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def q(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LateFeeTerms:
    type: str  # pct_monthly | pct_flat | fixed | none
    value: Decimal
    grace_days: int
    cap: Decimal | None


def fee_start(due: date, terms: LateFeeTerms) -> date:
    """First day a late fee may be charged."""
    return due + timedelta(days=terms.grace_days + 1)


def compute(terms: LateFeeTerms, amount: Decimal, due: date, today: date) -> Decimal:
    """Late fee owed on an unpaid invoice of `amount` due on `due`, as of `today`.

    pct_monthly: value% of amount per started 30-day period past due+grace.
    pct_flat:    value% of amount once, after due+grace.
    fixed:       value once, after due+grace.
    Result is capped at `cap` and rounded half-up to cents.
    """
    if terms.type == "none" or today < fee_start(due, terms):
        return Decimal("0.00")
    if terms.type == "pct_monthly":
        days_late = (today - (due + timedelta(days=terms.grace_days))).days
        months = -(-days_late // 30)  # ceil
        fee = amount * terms.value / 100 * months
    elif terms.type == "pct_flat":
        fee = amount * terms.value / 100
    elif terms.type == "fixed":
        fee = terms.value
    else:
        raise ValueError(f"unknown late fee type {terms.type}")
    if terms.cap is not None:
        fee = min(fee, terms.cap)
    return q(fee)
