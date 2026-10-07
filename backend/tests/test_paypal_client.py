import json
from datetime import date
from decimal import Decimal as D

import httpx
import pytest
import respx

from app.paypal import invoices, payouts, webhooks
from app.paypal.client import PayPalClient, PayPalError
from tests.conftest import SANDBOX


def client() -> PayPalClient:
    return PayPalClient(SANDBOX, "id", "secret")


def test_refuses_live_url() -> None:
    with pytest.raises(RuntimeError):
        PayPalClient("https://api-m.paypal.com", "id", "secret")


def test_token_cached_and_request_id_sent(pp: respx.MockRouter) -> None:
    route = pp.post("/v2/invoicing/generate-next-invoice-number").respond(
        json={"invoice_number": "0001"}
    )
    c = client()
    c.post("/v2/invoicing/generate-next-invoice-number", "rid-1")
    c.post("/v2/invoicing/generate-next-invoice-number", "rid-2")
    assert pp.routes[0].call_count == 1  # token fetched once
    sent = [call.request.headers["PayPal-Request-Id"] for call in route.calls]
    assert sent == ["rid-1", "rid-2"]
    assert route.calls[0].request.headers["Authorization"] == "Bearer A21-test"


def test_error_carries_debug_id(pp: respx.MockRouter) -> None:
    pp.post("/v2/invoicing/invoices").respond(
        403, json={"name": "NOT_AUTHORIZED", "message": "nope", "debug_id": "dbg123"}
    )
    with pytest.raises(PayPalError) as e:
        client().post("/v2/invoicing/invoices", "rid")
    assert (
        e.value.debug_id == "dbg123" and e.value.status == 403 and e.value.name == "NOT_AUTHORIZED"
    )


def test_create_draft_and_status(pp: respx.MockRouter) -> None:
    create = pp.post("/v2/invoicing/invoices").respond(201, json={"id": "INV2-AAAA"})
    pp.get("/v2/invoicing/invoices/INV2-AAAA").respond(
        json={
            "id": "INV2-AAAA",
            "status": "PAID",
            "payments": {"paid_amount": {"value": "4000.00"}},
        }
    )
    c = client()
    draft = invoices.InvoiceDraft(
        "USD", D("4000"), "M1", "design", "client@x", date(2026, 11, 21), "note", "C2C-1-M1"
    )
    assert invoices.create_draft(c, "c2c-inv-1", draft) == "INV2-AAAA"
    body = json.loads(create.calls[0].request.read())
    assert body["items"][0]["unit_amount"]["value"] == "4000.00"
    assert body["detail"]["payment_term"]["due_date"] == "2026-11-21"
    st = invoices.get_status(c, "INV2-AAAA")
    assert st.status == "PAID" and st.paid_amount == D("4000.00")


def test_create_draft_minimal_href_shape(pp: respx.MockRouter) -> None:
    pp.post("/v2/invoicing/invoices").respond(
        201, json={"href": f"{SANDBOX}/v2/invoicing/invoices/INV2-BBBB"}
    )
    draft = invoices.InvoiceDraft("USD", D("1"), "x", "x", "c@x", date(2026, 1, 1), "", "r")
    assert invoices.create_draft(client(), "rid", draft) == "INV2-BBBB"


def test_payout_batch(pp: respx.MockRouter) -> None:
    route = pp.post("/v1/payments/payouts").respond(
        201, json={"batch_header": {"payout_batch_id": "B1"}}
    )
    items = [payouts.PayoutItem("c2c-po-1", "ana@x", D("600"), "USD", "share")]
    assert payouts.create_batch(client(), "c2c-batch-1", "subj", items) == "B1"
    req = route.calls[0].request
    assert req.headers["PayPal-Request-Id"] == "c2c-batch-1"
    assert json.loads(req.read())["sender_batch_header"]["sender_batch_id"] == "c2c-batch-1"


def test_webhook_verify(pp: respx.MockRouter) -> None:
    route = pp.post("/v1/notifications/verify-webhook-signature").mock(
        side_effect=[
            httpx.Response(200, json={"verification_status": "SUCCESS"}),
            httpx.Response(200, json={"verification_status": "FAILURE"}),
        ]
    )
    h = {
        "PAYPAL-AUTH-ALGO": "a",
        "PAYPAL-CERT-URL": "u",
        "PAYPAL-TRANSMISSION-ID": "t",
        "PAYPAL-TRANSMISSION-SIG": "s",
        "PAYPAL-TRANSMISSION-TIME": "tt",
    }
    assert webhooks.verify(client(), h, {"id": "WH-1"}, "WHID") is True
    assert webhooks.verify(client(), h, {"id": "WH-1"}, "WHID") is False
    assert webhooks.verify(client(), {}, {"id": "WH-1"}, "WHID") is False  # no headers: no call
    assert route.call_count == 2
