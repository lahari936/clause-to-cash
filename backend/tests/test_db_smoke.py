"""Needs a migrated Postgres (docker compose up -d db && alembic upgrade head)."""

from decimal import Decimal

from sqlalchemy import inspect

from app.db.models import Base, Contract, GuardEvent, Milestone
from app.db.session import SessionLocal, engine


def test_all_tables_exist() -> None:
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())


def test_money_roundtrips_as_decimal() -> None:
    with SessionLocal() as db:
        c = Contract(title="smoke", file_key="k", sha256="0" * 64)
        db.add(c)
        db.flush()
        m = Milestone(contract_id=c.id, seq=1, title="t", deliverable="d", amount=Decimal("0.10"))
        g = GuardEvent(actor="test", action="noop", payload_json={}, decision="DENY",
                       rule_ids=["G1", "G10"], reason="smoke")
        db.add_all([m, g])
        db.flush()
        db.expire_all()
        assert db.get(Milestone, m.id).amount == Decimal("0.10")  # type: ignore[union-attr]
        assert db.get(GuardEvent, g.id).rule_ids == ["G1", "G10"]  # type: ignore[union-attr]
        db.rollback()
