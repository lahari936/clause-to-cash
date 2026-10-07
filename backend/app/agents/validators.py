"""Deterministic post-extraction checks (no LLM). Failures become review flags, not fixes."""

import re
from decimal import Decimal
from difflib import SequenceMatcher

from app.schemas.extraction import Cited, ContractExtraction

# Currencies PayPal Invoicing accepts (subset relevant to freelancers).
PAYPAL_CURRENCIES = {
    "AUD", "BRL", "CAD", "CHF", "CZK", "DKK", "EUR", "GBP", "HKD", "HUF", "ILS", "JPY", "MXN",
    "NOK", "NZD", "PHP", "PLN", "SEK", "SGD", "THB", "TWD", "USD",
}  # fmt: skip


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def quote_score(quote: str, page_text: str) -> float:
    """Best fuzzy match of quote against any same-length window of the page (1.0 = verbatim)."""
    q, p = _norm(quote), _norm(page_text)
    if not q:
        return 0.0
    if q in p:
        return 1.0
    n, step = len(q), max(1, len(q) // 8)
    best = 0.0
    for i in range(0, max(1, len(p) - n + 1), step):
        best = max(best, SequenceMatcher(None, q, p[i : i + n]).ratio())
    return best


def cites(x: ContractExtraction) -> dict[str, Cited]:
    """Field path -> citation, for every cited field (paths match extraction_fields.path)."""
    out: dict[str, Cited] = {"total_amount": x.total_cite, "net_days": x.net_days_cite}
    out |= {f"parties[{i}]": p.cite for i, p in enumerate(x.parties)}
    out |= {f"milestones[{i}]": m.cite for i, m in enumerate(x.milestones)}
    if x.late_fee.cite:
        out["late_fee"] = x.late_fee.cite
    if x.auto_accept_cite:
        out["auto_accept_days"] = x.auto_accept_cite
    if x.dispute_clause:
        out["dispute_clause"] = x.dispute_clause
    return out


def validate(x: ContractExtraction, pages: list[str]) -> dict[str, str]:
    """Return {field path: problem} for every deterministic check that fails."""
    flags: dict[str, str] = {}
    ms_sum = sum((m.amount for m in x.milestones), Decimal(0))
    expected = x.total_amount - (x.deposit_amount or Decimal(0))
    if ms_sum != expected:
        flags["total_amount"] = f"milestones sum to {ms_sum} but total minus deposit is {expected}"
    if x.currency.upper() not in PAYPAL_CURRENCIES:
        flags["currency"] = f"{x.currency} is not supported by PayPal Invoicing"
    shares = sum((p.share_pct or Decimal(0) for p in x.parties), Decimal(0))
    if shares > 100:
        flags["parties"] = f"subcontractor shares total {shares}% (> 100%)"
    if not any(p.role == "client" for p in x.parties):
        flags["parties"] = "no client party found"
    for path, c in cites(x).items():
        if not 1 <= c.page <= len(pages):
            flags[path] = f"cited page {c.page} does not exist"
        elif (score := quote_score(c.quote, pages[c.page - 1])) < 0.9:
            flags[path] = f"quote not found on page {c.page} (match {score:.2f})"
    return flags
