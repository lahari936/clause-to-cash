from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect

from app.db.models import Base

SKIP = {"pdf", "pages_json", "evidence_pdf", "raw_json"}


def row(obj: Base, **extra: Any) -> dict[str, Any]:
    """Plain dict of loaded columns; Decimal -> str so money never becomes a float."""
    out: dict[str, Any] = {}
    for col in sa_inspect(obj).mapper.column_attrs:
        if col.key in SKIP:
            continue
        v = getattr(obj, col.key)
        out[col.key] = str(v) if isinstance(v, Decimal) else v
    return out | extra
