from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.paypal.client import JSON, PayPalClient


@dataclass(frozen=True)
class InvoiceDraft:
    currency: str
    amount: Decimal
    item_name: str
    item_description: str
    recipient_email: str
    due_date: date
    note: str  # shown to the client: contract, milestone, cited clause
    reference: str


@dataclass(frozen=True)
class InvoiceStatus:
    id: str
    status: str
    paid_amount: Decimal | None


def create_draft(pp: PayPalClient, request_id: str, d: InvoiceDraft) -> str:
    body: JSON = {
        "detail": {
            "currency_code": d.currency,
            "note": d.note[:4000],
            "reference": d.reference[:120],
            "payment_term": {
                "term_type": "DUE_ON_DATE_SPECIFIED",
                "due_date": d.due_date.isoformat(),
            },
        },
        "primary_recipients": [{"billing_info": {"email_address": d.recipient_email}}],
        "items": [
            {
                "name": d.item_name[:200],
                "description": d.item_description[:1000],
                "quantity": "1",
                "unit_amount": {"currency_code": d.currency, "value": f"{d.amount:.2f}"},
                "unit_of_measure": "AMOUNT",
            }
        ],
    }
    res = pp.post("/v2/invoicing/invoices", request_id, body, prefer_full=True)
    if "id" in res:
        return str(res["id"])
    return str(res["href"]).rstrip("/").split("/")[-1]  # older "return=minimal" shape


def send(pp: PayPalClient, request_id: str, invoice_id: str) -> None:
    pp.post(
        f"/v2/invoicing/invoices/{invoice_id}/send",
        request_id,
        {"send_to_invoicer": True, "send_to_recipient": True},
    )


def remind(pp: PayPalClient, request_id: str, invoice_id: str, subject: str, note: str) -> None:
    pp.post(
        f"/v2/invoicing/invoices/{invoice_id}/remind",
        request_id,
        {"subject": subject[:100], "note": note[:4000], "send_to_invoicer": True},
    )


def get_status(pp: PayPalClient, invoice_id: str) -> InvoiceStatus:
    res = pp.get(f"/v2/invoicing/invoices/{invoice_id}")
    paid = res.get("payments", {}).get("paid_amount", {}).get("value")
    return InvoiceStatus(invoice_id, str(res["status"]), Decimal(paid) if paid else None)
