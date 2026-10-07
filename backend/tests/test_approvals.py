from decimal import Decimal as D

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import GuardEvent, Invoice, Milestone
from app.main import app
from app.services import approvals, milestones
from tests.conftest import approved_contract, mock_invoicing

api = TestClient(app)


def _pending(db, llm, pp):  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm, threshold=D("1000.00"))  # M1 = 4000 > threshold
    llm.on("AcceptanceResult", {"meets_criteria": True, "gaps": [], "summary_for_client": "ok"})
    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 1)).one()
    milestones.deliver(db, m, "done", [])
    out = milestones.accept(db, m, "owner")
    db.commit()
    return out


def test_over_threshold_waits_for_human(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    out = _pending(db, llm, pp)
    assert out.decision.decision == "NEEDS_APPROVAL" and out.decision.rule_ids == ["G9"]
    assert db.scalars(select(Invoice)).all() == []
    assert pp.routes[1].call_count == 0  # nothing sent to PayPal

    r = api.get("/guard/events", params={"pending": True}).json()
    assert [e["id"] for e in r] == [out.decision.event_id]

    r = api.post(f"/guard/events/{out.decision.event_id}/approve", json={"by": "owner"})
    assert r.status_code == 200 and r.json()["decision"] == "ALLOW"
    inv = db.scalars(select(Invoice)).one()
    assert inv.status == "SENT" and inv.amount == D("4000.00")
    db.expire_all()
    ev = db.get(GuardEvent, out.decision.event_id)
    assert (ev.resolution, ev.approved_by) == ("approved", "owner")
    # cannot approve twice
    assert api.post(f"/guard/events/{ev.id}/approve", json={"by": "x"}).status_code == 409


def test_reject(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    out = _pending(db, llm, pp)
    approvals.reject(db, out.decision.event_id, "owner")
    db.commit()
    with pytest.raises(approvals.ApprovalError):
        approvals.approve(db, out.decision.event_id, "owner")
    assert db.scalars(select(Invoice)).all() == []
