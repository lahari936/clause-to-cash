from datetime import date, timedelta

from app.config import get_settings

_override: date | None = None


def today() -> date:
    """Business 'today'. DEMO_CLOCK (YYYY-MM-DD) or the runtime override fast-forwards time."""
    if _override:
        return _override
    if clock := get_settings().demo_clock:
        return date.fromisoformat(clock)
    return date.today()


def set_today(d: date | None) -> None:
    global _override
    _override = d


def due_date(issued: date, net_days: int) -> date:
    return issued + timedelta(days=net_days)
