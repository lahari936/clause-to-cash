import hashlib

from app.paypal.client import JSON, PayPalClient

HEADERS = {
    "auth_algo": "paypal-auth-algo",
    "cert_url": "paypal-cert-url",
    "transmission_id": "paypal-transmission-id",
    "transmission_sig": "paypal-transmission-sig",
    "transmission_time": "paypal-transmission-time",
}


def verify(pp: PayPalClient, headers: dict[str, str], event: JSON, webhook_id: str) -> bool:
    """Ask PayPal whether this delivery is authentic. Missing headers or webhook id -> False."""
    h = {k.lower(): v for k, v in headers.items()}
    if not webhook_id or any(name not in h for name in HEADERS.values()):
        return False
    body: JSON = {k: h[name] for k, name in HEADERS.items()}
    body |= {"webhook_id": webhook_id, "webhook_event": event}
    rid = "verify-" + hashlib.sha256(h["paypal-transmission-id"].encode()).hexdigest()[:32]
    res = pp.post("/v1/notifications/verify-webhook-signature", rid, body)
    return res.get("verification_status") == "SUCCESS"
