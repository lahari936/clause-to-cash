"""Guard rules G1-G10. Each is a pure function (action, mandate, state) -> RuleResult."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.guard.mandate import Action, MandateView, State
from app.money import late_fee, splits

Outcome = Literal["pass", "deny", "approval"]


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    outcome: Outcome
    reason: str = ""


def _ok(rid: str) -> RuleResult:
    return RuleResult(rid, "pass")


def _deny(rid: str, reason: str) -> RuleResult:
    return RuleResult(rid, "deny", reason)


INVOICE_KINDS = ("milestone_invoice", "late_fee_invoice", "remind")


def g1_mandate(a: Action, m: MandateView | None, s: State) -> RuleResult:
    if m is None:
        return _deny("G1", "no approved mandate for this contract")
    if m.contract_status != "approved":
        return _deny("G1", f"contract status is {m.contract_status}, not approved")
    return _ok("G1")


def g2_payee(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.kind in INVOICE_KINDS:
        if a.recipient.lower() != m.client_email.lower():
            return _deny("G2", f"{a.recipient} is not the mandate client")
        return _ok("G2")
    p = m.parties.get(a.party_id) if a.party_id is not None else None
    if p is None or p.role != "subcontractor" or p.email.lower() != a.recipient.lower():
        return _deny("G2", f"{a.recipient} is not a subcontractor in the mandate")
    return _ok("G2")


def g3_currency(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.currency != m.currency:
        return _deny("G3", f"currency {a.currency} != mandate currency {m.currency}")
    return _ok("G3")


def g4_milestone_amount(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.kind != "milestone_invoice":
        return _ok("G4")
    ms = m.milestones.get(a.milestone_id) if a.milestone_id is not None else None
    if ms is None:
        return _deny("G4", "no contracted milestone for this invoice")
    if a.amount != ms.amount:
        return _deny("G4", f"amount {a.amount} != contracted milestone amount {ms.amount}")
    if ms.status != "accepted":
        return _deny("G4", f"milestone status is {ms.status}, not accepted")
    return _ok("G4")


def g5_total_cap(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.kind != "milestone_invoice":
        return _ok("G5")
    if s.invoiced_total + a.amount > m.total:
        return _deny(
            "G5", f"would invoice {s.invoiced_total + a.amount} > contract total {m.total}"
        )
    return _ok("G5")


def g6_late_fee(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.kind != "late_fee_invoice":
        return _ok("G6")
    inv = s.invoice
    if inv is None or inv.kind != "milestone" or inv.due_date is None:
        return _deny("G6", "late fee must reference an issued milestone invoice")
    if inv.status == "PAID":
        return _deny("G6", "invoice already paid")
    if s.today < late_fee.fee_start(inv.due_date, m.late_fee):
        return _deny("G6", "still inside due date + grace period")
    want = late_fee.compute(m.late_fee, inv.amount, inv.due_date, s.today)
    if want <= 0 or a.amount != want:
        return _deny("G6", f"late fee {a.amount} != contract-correct {want}")
    return _ok("G6")


def g7_payout(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.kind != "payout":
        return _ok("G7")
    inv = s.invoice
    if inv is None or inv.kind != "milestone" or inv.status != "PAID":
        return _deny("G7", "payouts only after the client's milestone invoice is PAID")
    p = m.parties.get(a.party_id) if a.party_id is not None else None
    if p is None or not p.share_pct:
        return _deny("G7", "party has no revenue share")
    want = splits.share(inv.paid_amount or inv.amount, p.share_pct)
    if a.amount != want:
        return _deny("G7", f"payout {a.amount} != {p.share_pct}% share {want}")
    return _ok("G7")


def g8_duplicate(a: Action, m: MandateView | None, s: State) -> RuleResult:
    if s.already_executed:
        return _deny("G8", "this action was already executed")
    return _ok("G8")


def g9_threshold(a: Action, m: MandateView | None, s: State) -> RuleResult:
    assert m
    if a.amount > m.approval_threshold and not s.approved_by:
        return RuleResult(
            "G9", "approval", f"{a.amount} > approval threshold {m.approval_threshold}"
        )
    return _ok("G9")


def g10_traceable(a: Action, m: MandateView | None, s: State) -> RuleResult:
    if a.source != "free_text":
        return _ok("G10")
    ref = {
        "milestone_invoice": a.milestone_id,
        "late_fee_invoice": a.invoice_id,
        "payout": a.invoice_id,
        "remind": a.invoice_id,
    }[a.kind]
    if ref is None:
        return _deny("G10", "instruction is not traceable to a mandate rule")
    return _ok("G10")


Rule = Callable[[Action, MandateView | None, State], RuleResult]
RULES: list[Rule] = [
    g2_payee, g3_currency, g4_milestone_amount, g5_total_cap, g6_late_fee,
    g7_payout, g8_duplicate, g9_threshold, g10_traceable,
]  # fmt: skip


def evaluate(a: Action, m: MandateView | None, s: State) -> list[RuleResult]:
    first = g1_mandate(a, m, s)
    if first.outcome == "deny":
        return [first, g10_traceable(a, m, s)]
    return [first] + [r(a, m, s) for r in RULES]
