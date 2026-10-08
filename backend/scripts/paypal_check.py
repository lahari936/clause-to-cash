"""Phase 0.3 check: get a sandbox token and generate (not create) an invoice number."""

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    if not s.paypal_client_id or s.paypal_client_id.startswith("your-"):
        sys.exit("Set PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET in .env first.")
    with httpx.Client(base_url=s.paypal_base_url, timeout=30) as http:
        tok = http.post(
            "/v1/oauth2/token",
            auth=(s.paypal_client_id, s.paypal_client_secret),
            data={"grant_type": "client_credentials"},
        )
        tok.raise_for_status()
        body = tok.json()
        print(f"token ok, expires_in={body['expires_in']}s")
        num = http.post(
            "/v2/invoicing/generate-next-invoice-number",
            json={},
            headers={
                "Authorization": f"Bearer {body['access_token']}",
                "PayPal-Request-Id": f"paypal-check-{uuid.uuid4()}",
            },
        )
        num.raise_for_status()
        print(f"next invoice number: {num.json()['invoice_number']}")


if __name__ == "__main__":
    main()
