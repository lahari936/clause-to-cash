from dataclasses import dataclass
from decimal import Decimal

from app.paypal.client import PayPalClient


@dataclass(frozen=True)
class PayoutItem:
    sender_item_id: str  # our payout row request_id
    receiver: str
    amount: Decimal
    currency: str
    note: str


@dataclass(frozen=True)
class ItemStatus:
    sender_item_id: str
    payout_item_id: str
    status: str  # SUCCESS, PENDING, UNCLAIMED, FAILED ...


def create_batch(
    pp: PayPalClient, sender_batch_id: str, subject: str, items: list[PayoutItem]
) -> str:
    body = {
        "sender_batch_header": {"sender_batch_id": sender_batch_id, "email_subject": subject},
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": i.receiver,
                "amount": {"value": f"{i.amount:.2f}", "currency": i.currency},
                "note": i.note[:4000],
                "sender_item_id": i.sender_item_id,
            }
            for i in items
        ],
    }
    res = pp.post("/v1/payments/payouts", sender_batch_id, body)
    return str(res["batch_header"]["payout_batch_id"])


def get_batch(pp: PayPalClient, batch_id: str) -> tuple[str, list[ItemStatus]]:
    res = pp.get(f"/v1/payments/payouts/{batch_id}")
    items = [
        ItemStatus(
            str(it.get("payout_item", {}).get("sender_item_id", "")),
            str(it.get("payout_item_id", "")),
            str(it.get("transaction_status", "PENDING")),
        )
        for it in res.get("items", [])
    ]
    return str(res["batch_header"]["batch_status"]), items
