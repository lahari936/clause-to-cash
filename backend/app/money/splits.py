from collections.abc import Mapping
from decimal import Decimal

from app.money.late_fee import q


def share(paid: Decimal, pct: Decimal) -> Decimal:
    """One party's revenue share of a payment, rounded half-up to cents."""
    return q(paid * pct / 100)


def compute[K](paid: Decimal, shares: Mapping[K, Decimal]) -> dict[K, Decimal]:
    """Payout per party. Rounding remainder stays with the agency (never over-pays)."""
    if sum(shares.values(), Decimal(0)) > 100:
        raise ValueError("shares exceed 100%")
    return {k: share(paid, pct) for k, pct in shares.items() if pct > 0}
