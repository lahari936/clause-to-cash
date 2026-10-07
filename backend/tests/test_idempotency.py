"""Regression tests for the checker's double-payment findings: retries replay the same
PayPal-Request-Id, stale/concurrent processors can't pay twice, webhooks are redelivered safely."""

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Dispute, Invoice, Milestone, Payout
from app.db.session import SessionLocal
from app.main import app
from app.paypal.client import PayPalError
from app.services import disputes, invoicing, milestones, payouts
from tests.conftest import approved_contract, mock_invoicing

ACCEPT = {"meets_criteria": True, "gaps": [], "summary_for_client": "ok"}
api = TestClient(app)


def _m1(db, llm):  # type: ignore[no-untyped-def]
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", ACCEPT)
    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 1)).one()
    milestones.deliver(db, m, "done", [])
    return m


def test_timeout_then_retry_replays_same_request(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    m = _m1(db, llm)
    create = pp.post("/v2/invoicing/invoices").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(201, json={"id": "INV2-ONE"})]
    )
    send = pp.post(url__regex=r".*/invoices/INV2-ONE/send").respond(200, json={})
    with pytest.raises(PayPalError):  # timeout surfaces as a PayPalError, row kept as FAILED
        milestones.accept(db, m, "owner")
    db.commit()
    assert db.scalars(select(Invoice)).one().status == "FAILED"

    out = milestones.accept(db, m, "owner")  # retry (e.g. "Retry invoice" button)
    db.commit()
    assert out.decision.decision == "ALLOW"
    keys = [c.request.headers["PayPal-Request-Id"] for c in create.calls]
    assert keys == [f"c2c-inv-m{m.id}"] * 2  # PayPal dedupes the replay
    assert len(db.scalars(select(Invoice)).all()) == 1 and send.call_count == 1


def test_send_failure_reuses_existing_draft(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    m = _m1(db, llm)
    create = pp.post("/v2/invoicing/invoices").respond(201, json={"id": "INV2-DRAFT"})
    pp.post(url__regex=r".*/send").mock(
        side_effect=[httpx.Response(500, json={"name": "INTERNAL"}), httpx.Response(200, json={})]
    )
    with pytest.raises(PayPalError):
        milestones.accept(db, m, "owner")
    db.commit()
    milestones.accept(db, m, "owner")
    db.commit()
    assert create.call_count == 1  # no orphan second draft
    inv = db.scalars(select(Invoice)).one()
    assert (inv.status, inv.paypal_invoice_id) == ("SENT", "INV2-DRAFT")


def _paid_setup(db, llm, pp):  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    m = _m1(db, llm)
    milestones.accept(db, m, "owner")
    db.commit()
    inv = db.scalars(select(Invoice)).one()
    pp.get(f"/v2/invoicing/invoices/{inv.paypal_invoice_id}").respond(
        json={"status": "PAID", "payments": {"paid_amount": {"value": "4000.00"}}}
    )
    return inv


def test_stale_second_processor_does_not_pay_twice(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _paid_setup(db, llm, pp)
    with SessionLocal() as other:  # e.g. the poll job, loaded before the webhook committed
        stale = other.get(Invoice, inv.id)
        assert stale.status == "SENT"
        invoicing.sync_invoice(db, inv)  # webhook path wins
        db.commit()
        assert invoicing.mark_paid(other, stale, None) is False  # lock + re-read sees PAID
        other.commit()
    assert pp.routes[4].call_count == 1  # exactly one payout batch
    assert len(db.scalars(select(Payout)).all()) == 2


def test_failed_payout_retry_uses_same_keys(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _paid_setup(db, llm, pp)
    batch = pp.routes[4]
    batch.side_effect = [
        httpx.ReadTimeout("slow"),
        httpx.Response(201, json={"batch_header": {"payout_batch_id": "B-OK"}}),
    ]
    invoicing.sync_invoice(db, inv)  # PAID; payout batch times out -> rows FAILED
    db.commit()
    assert {p.status for p in db.scalars(select(Payout))} == {"FAILED"}
    payouts.retry_failed(db)
    db.commit()
    rows = db.scalars(select(Payout).order_by(Payout.id)).all()
    assert len(rows) == 2 and {p.status for p in rows} == {"SENT"}
    ids = [
        json.loads(c.request.read())["sender_batch_header"]["sender_batch_id"] for c in batch.calls
    ]
    assert ids[0] == ids[1]  # PayPal replays rather than paying again
    assert [c.request.headers["PayPal-Request-Id"] for c in batch.calls] == ids


SIG = {
    "PAYPAL-AUTH-ALGO": "a",
    "PAYPAL-CERT-URL": "u",
    "PAYPAL-TRANSMISSION-ID": "tx",
    "PAYPAL-TRANSMISSION-SIG": "s",
    "PAYPAL-TRANSMISSION-TIME": "t",
}


def test_webhook_redelivery_after_failure_is_processed(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    m = _m1(db, llm)
    milestones.accept(db, m, "owner")
    db.commit()
    inv = db.scalars(select(Invoice)).one()
    pp.post("/v1/notifications/verify-webhook-signature").respond(
        json={"verification_status": "SUCCESS"}
    )
    pp.get(f"/v2/invoicing/invoices/{inv.paypal_invoice_id}").mock(
        side_effect=[
            httpx.Response(503, json={"name": "SERVICE_UNAVAILABLE"}),
            httpx.Response(
                200, json={"status": "PAID", "payments": {"paid_amount": {"value": "4000.00"}}}
            ),
        ]
    )
    ev = {
        "id": "WH-R",
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": inv.paypal_invoice_id}},
    }
    assert api.post("/webhooks/paypal", content=json.dumps(ev), headers=SIG).status_code == 502
    r = api.post("/webhooks/paypal", content=json.dumps(ev), headers=SIG)  # PayPal redelivers
    assert r.json() == {"status": "PAID"}
    assert api.post("/webhooks/paypal", content=json.dumps(ev), headers=SIG).json() == {
        "status": "duplicate"
    }


def test_unmatched_dispute_is_not_pinned_on_another_invoice(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _paid_setup(db, llm, pp)
    invoicing.sync_invoice(db, inv)
    db.commit()
    d = disputes.open_dispute(
        db,
        "PP-D-1",
        {"reason": "X", "disputed_transactions": [{"seller_transaction_id": "9XYZ"}]},
        dry_run=False,
    )
    db.commit()
    assert d.invoice_id is None and d.evidence_pdf is None
    db.expire_all()
    assert db.get(Milestone, inv.milestone_id).status == "paid"
    assert db.scalars(select(Dispute)).one().contract_id is None


def test_second_payout_failure_stops_for_review(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _paid_setup(db, llm, pp)
    pp.routes[4].side_effect = httpx.ReadTimeout("slow")
    invoicing.sync_invoice(db, inv)
    db.commit()
    payouts.retry_failed(db)
    db.commit()
    payouts.retry_failed(db)  # nothing left to retry automatically
    db.commit()
    assert {p.status for p in db.scalars(select(Payout))} == {"NEEDS_REVIEW"}
    assert pp.routes[4].call_count == 2


def test_webhook_dispatches_only_the_verified_body(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    pp.post("/v1/notifications/verify-webhook-signature").mock(
        side_effect=[
            httpx.Response(200, json={"verification_status": "FAILURE"}),
            httpx.Response(200, json={"verification_status": "SUCCESS"}),
        ]
    )
    forged = {
        "id": "WH-F",
        "event_type": "CUSTOMER.DISPUTE.CREATED",
        "resource": {"dispute_id": "EVIL"},
    }
    real = {"id": "WH-F", "event_type": "PING", "resource": {}}
    api.post("/webhooks/paypal", content=json.dumps(forged), headers=SIG)
    r = api.post("/webhooks/paypal", content=json.dumps(real), headers=SIG)
    assert r.json() == {"status": "ignored"}  # the verified (real) body was dispatched
    assert db.scalars(select(Dispute)).all() == []
