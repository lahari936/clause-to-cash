import json

import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Invoice, WebhookEvent
from app.main import app
from app.services import milestones
from tests.conftest import approved_contract, mock_invoicing

api = TestClient(app)
SIG = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/c",
    "PAYPAL-TRANSMISSION-ID": "tx-1",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-01T00:00:00Z",
}


def _invoice(db, llm, pp):  # type: ignore[no-untyped-def]
    mock_invoicing(pp)
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", {"meets_criteria": True, "gaps": [], "summary_for_client": "ok"})
    from app.db.models import Milestone

    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 1)).one()
    milestones.deliver(db, m, "done", [])
    milestones.accept(db, m, "owner")
    db.commit()
    return db.scalars(select(Invoice)).one()


def _event(inv_id: str, eid: str = "WH-1") -> dict:  # type: ignore[type-arg]
    return {
        "id": eid,
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": inv_id, "status": "PAID"}},
    }


def test_verified_paid_event_marks_paid_once(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _invoice(db, llm, pp)
    verify = pp.post("/v1/notifications/verify-webhook-signature").respond(
        json={"verification_status": "SUCCESS"}
    )
    pp.get(f"/v2/invoicing/invoices/{inv.paypal_invoice_id}").respond(
        json={"status": "PAID", "payments": {"paid_amount": {"value": "4000.00"}}}
    )

    r = api.post("/webhooks/paypal", content=json.dumps(_event(inv.paypal_invoice_id)), headers=SIG)
    assert r.json() == {"status": "PAID"}
    sent = json.loads(verify.calls[0].request.read())
    assert sent["webhook_id"] == "WH-TEST" and sent["transmission_id"] == "tx-1"

    r = api.post("/webhooks/paypal", content=json.dumps(_event(inv.paypal_invoice_id)), headers=SIG)
    assert r.json() == {"status": "duplicate"}
    db.expire_all()
    assert db.get(Invoice, inv.id).status == "PAID"
    ev = db.get(WebhookEvent, "WH-1")
    assert ev.verified and ev.processed_at is not None


def test_unverified_event_stored_not_processed(db, llm, pp: respx.MockRouter) -> None:  # type: ignore[no-untyped-def]
    inv = _invoice(db, llm, pp)
    pp.post("/v1/notifications/verify-webhook-signature").respond(
        json={"verification_status": "FAILURE"}
    )
    r = api.post(
        "/webhooks/paypal", content=json.dumps(_event(inv.paypal_invoice_id, "WH-2")), headers=SIG
    )
    assert r.json() == {"status": "stored-unverified"}
    db.expire_all()
    assert db.get(Invoice, inv.id).status == "SENT"
    ev = db.get(WebhookEvent, "WH-2")
    assert ev.verified is False and ev.processed_at is None


def test_simulated_event_without_signature(db) -> None:  # type: ignore[no-untyped-def]
    """simulate-event deliveries can't be verified: stored, never acted on (poll job covers)."""
    r = api.post("/webhooks/paypal", content=json.dumps(_event("INV2-X", "WH-SIM")))
    assert r.json() == {"status": "stored-unverified"}


def test_bad_payload(db) -> None:  # type: ignore[no-untyped-def]
    assert api.post("/webhooks/paypal", content="nope").status_code == 400
