from datetime import date
from decimal import Decimal as D

from sqlalchemy import select

from app.db.models import GuardEvent
from app.guard import Action, check
from app.guard.engine import decide
from app.guard.mandate import InvoiceView, MandateView, MilestoneView, PartyView, State
from app.guard.rules import evaluate
from app.money.late_fee import LateFeeTerms
from tests.conftest import approved_contract

CLIENT = "client@test.example"
M = MandateView(
    contract_status="approved",
    currency="USD",
    total=D("10000.00"),
    client_email=CLIENT,
    approval_threshold=D("5000.00"),
    late_fee=LateFeeTerms("pct_monthly", D("1.5"), 5, D("500.00")),
    parties={1: PartyView("client", CLIENT, None), 2: PartyView("subcontractor", "ana@x", D("15"))},
    milestones={
        10: MilestoneView(D("4000.00"), "accepted"),
        11: MilestoneView(D("3500.00"), "planned"),
    },
)
S = State(today=date(2026, 11, 1), invoiced_total=D("0"), already_executed=False)


def inv(**kw: object) -> Action:
    base: dict[str, object] = dict(
        kind="milestone_invoice",
        contract_id=1,
        amount=D("4000.00"),
        currency="USD",
        recipient=CLIENT,
        milestone_id=10,
    )
    return Action(**(base | kw))  # type: ignore[arg-type]


def verdict(a: Action, m: MandateView | None = M, s: State = S) -> tuple[str, list[str]]:
    kind, why = decide(evaluate(a, m, s))
    return kind, [r.rule_id for r in why]


def test_allow_exact_milestone_invoice() -> None:
    assert verdict(inv()) == ("ALLOW", [])


def test_g1_no_mandate() -> None:
    assert verdict(inv(), m=None)[1] == ["G1"]


def test_g1_contract_not_approved() -> None:
    from dataclasses import replace

    assert verdict(inv(), m=replace(M, contract_status="review"))[1] == ["G1"]


def test_g2_wrong_payee() -> None:
    assert verdict(inv(recipient="attacker@evil.example")) == ("DENY", ["G2"])


def test_g3_currency() -> None:
    assert verdict(inv(currency="EUR")) == ("DENY", ["G3"])


def test_g4_amount_mismatch_and_status() -> None:
    assert verdict(inv(amount=D("4000.01")))[1] == ["G4"]
    assert verdict(inv(milestone_id=11, amount=D("3500.00")))[1] == ["G4"]  # not accepted


def test_g5_total_cap() -> None:
    from dataclasses import replace

    assert verdict(inv(), s=replace(S, invoiced_total=D("6500.01")))[1] == ["G5"]


def test_g6_late_fee() -> None:
    from dataclasses import replace

    sent = InvoiceView("milestone", D("4000.00"), "SENT", date(2026, 11, 21), None)
    fee = inv(kind="late_fee_invoice", milestone_id=None, invoice_id=5, amount=D("60.00"))
    in_grace = replace(S, today=date(2026, 11, 26), invoice=sent)
    after = replace(S, today=date(2026, 11, 27), invoice=sent)
    assert verdict(fee, s=in_grace)[1] == ["G6"]
    assert verdict(fee, s=after) == ("ALLOW", [])
    assert verdict(replace(fee, amount=D("61.00")), s=after)[1] == ["G6"]
    paid = replace(after, invoice=replace(sent, status="PAID"))
    assert verdict(fee, s=paid)[1] == ["G6"]


def test_g7_payout_share_only_after_paid() -> None:
    from dataclasses import replace

    paid = InvoiceView("milestone", D("4000.00"), "PAID", date(2026, 11, 21), D("4000.00"))
    po = Action("payout", 1, D("600.00"), "USD", "ana@x", invoice_id=5, party_id=2)
    assert verdict(po, s=replace(S, invoice=paid)) == ("ALLOW", [])
    assert verdict(replace(po, amount=D("700.00")), s=replace(S, invoice=paid))[1] == ["G7"]
    unpaid = replace(S, invoice=replace(paid, status="SENT"))
    assert verdict(po, s=unpaid)[1] == ["G7"]
    assert "G2" in verdict(replace(po, recipient="x@evil"), s=replace(S, invoice=paid))[1]


def test_g8_duplicate() -> None:
    from dataclasses import replace

    assert verdict(inv(), s=replace(S, already_executed=True))[1] == ["G8"]


def test_g9_threshold_needs_approval_then_allows() -> None:
    from dataclasses import replace

    low = replace(M, approval_threshold=D("1000.00"))
    assert verdict(inv(), m=low) == ("NEEDS_APPROVAL", ["G9"])
    assert verdict(inv(), m=low, s=replace(S, approved_by="owner")) == ("ALLOW", [])


def test_g10_free_text_untraceable() -> None:
    a = inv(milestone_id=None, amount=D("5000.00"), source="free_text")
    kind, rules = verdict(a)
    assert kind == "DENY" and {"G4", "G10"} <= set(rules)


def test_deny_beats_approval() -> None:
    from dataclasses import replace

    low = replace(M, approval_threshold=D("1"))
    assert verdict(inv(recipient="x@evil"), m=low)[0] == "DENY"


def test_check_writes_guard_event(db, llm) -> None:  # type: ignore[no-untyped-def]
    c = approved_contract(db, llm)
    a = Action("milestone_invoice", c.id, D("5000.00"), "USD", "x@evil.example", source="free_text")
    d = check(db, a, "copilot")
    db.commit()
    assert d.decision == "DENY"
    ev = db.scalars(select(GuardEvent)).one()
    assert ev.actor == "copilot" and ev.decision == "DENY"
    assert {"G2", "G4", "G10"} <= set(ev.rule_ids)
    assert ev.payload_json["amount"] == "5000.00"
