from datetime import date
from decimal import Decimal as D

import pytest

from app.money import dates, splits
from app.money.late_fee import LateFeeTerms, compute

DUE = date(2026, 11, 21)
MONTHLY = LateFeeTerms("pct_monthly", D("1.5"), 5, D("500.00"))


@pytest.mark.parametrize(
    ("today", "want"),
    [
        (date(2026, 11, 21), "0.00"),  # on due date
        (date(2026, 11, 26), "0.00"),  # last grace day
        (date(2026, 11, 27), "60.00"),  # first day after grace: 1 started month
        (date(2026, 12, 26), "60.00"),  # day 30 past grace
        (date(2026, 12, 27), "120.00"),  # day 31: 2nd month
        (date(2027, 6, 1), "420.00"),  # 7 months
        (date(2028, 1, 1), "500.00"),  # capped
    ],
)
def test_pct_monthly(today: date, want: str) -> None:
    assert compute(MONTHLY, D("4000.00"), DUE, today) == D(want)


def test_pct_monthly_no_cap_no_grace() -> None:
    t = LateFeeTerms("pct_monthly", D("2"), 0, None)
    assert compute(t, D("3000.00"), DUE, date(2026, 11, 22)) == D("60.00")
    assert compute(t, D("3000.00"), DUE, date(2027, 11, 22)) == D("780.00")  # 13 months, no cap


def test_pct_flat_once() -> None:
    t = LateFeeTerms("pct_flat", D("5"), 0, None)
    assert compute(t, D("4000.00"), DUE, DUE) == D("0.00")
    assert compute(t, D("4000.00"), DUE, date(2026, 11, 22)) == D("200.00")
    assert compute(t, D("4000.00"), DUE, date(2027, 5, 1)) == D("200.00")


def test_fixed_after_grace() -> None:
    t = LateFeeTerms("fixed", D("50.00"), 10, None)
    assert compute(t, D("2500.00"), DUE, date(2026, 12, 1)) == D("0.00")
    assert compute(t, D("2500.00"), DUE, date(2026, 12, 2)) == D("50.00")


def test_fixed_capped() -> None:
    t = LateFeeTerms("fixed", D("100.00"), 0, D("75.00"))
    assert compute(t, D("10.00"), DUE, date(2026, 12, 1)) == D("75.00")


def test_zero_fee_none_type() -> None:
    t = LateFeeTerms("none", D("0"), 0, None)
    assert compute(t, D("9999.99"), DUE, date(2030, 1, 1)) == D("0.00")


def test_rounding_half_up() -> None:
    t = LateFeeTerms("pct_flat", D("1.5"), 0, None)
    assert compute(t, D("0.99"), DUE, date(2026, 12, 1)) == D("0.01")  # 0.01485 -> 0.01
    assert compute(t, D("1.00"), DUE, date(2026, 12, 1)) == D("0.02")  # 0.015 -> 0.02


def test_unknown_type_raises() -> None:
    with pytest.raises(ValueError):
        compute(LateFeeTerms("weird", D("1"), 0, None), D("1"), DUE, date(2027, 1, 1))


def test_splits() -> None:
    assert splits.compute(D("4000.00"), {"ana": D("15"), "ben": D("10")}) == {
        "ana": D("600.00"),
        "ben": D("400.00"),
    }


def test_splits_rounding_never_overpays() -> None:
    out = splits.compute(D("100.01"), {"a": D("12.5"), "b": D("7.5")})
    assert out == {"a": D("12.50"), "b": D("7.50")}
    assert sum(out.values()) <= D("100.01")


def test_splits_reject_over_100() -> None:
    with pytest.raises(ValueError):
        splits.compute(D("1"), {"a": D("60"), "b": D("41")})


def test_splits_skip_zero_share() -> None:
    assert splits.compute(D("100"), {"a": D("0")}) == {}


def test_due_date() -> None:
    assert dates.due_date(date(2026, 12, 20), 15) == date(2027, 1, 4)


def test_demo_clock_override() -> None:
    dates.set_today(date(2027, 1, 1))
    try:
        assert dates.today() == date(2027, 1, 1)
    finally:
        dates.set_today(None)
    assert dates.today() != date(2027, 1, 1) or date.today() == date(2027, 1, 1)
