"""Minimal typed PayPal REST client (sandbox only). Token cached until expiry.

Every POST requires a PayPal-Request-Id derived from our DB row so retries are idempotent.
"""

import time
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings

JSON = dict[str, Any]


class PayPalError(Exception):
    def __init__(self, status: int, name: str, message: str, debug_id: str | None) -> None:
        super().__init__(f"PayPal {status} {name}: {message} (debug_id={debug_id})")
        self.status = status
        self.name = name
        self.message = message
        self.debug_id = debug_id


class PayPalClient:
    def __init__(
        self, base_url: str, client_id: str, secret: str, http: httpx.Client | None = None
    ) -> None:
        if "sandbox" not in base_url:
            raise RuntimeError(f"refusing non-sandbox PayPal URL {base_url}")
        self.http = http or httpx.Client(base_url=base_url, timeout=30)
        self.client_id = client_id
        self.secret = secret
        self._token: str | None = None
        self._expires = 0.0

    def token(self) -> str:
        if self._token and time.monotonic() < self._expires - 60:
            return self._token
        r = self.http.post(
            "/v1/oauth2/token",
            auth=(self.client_id, self.secret),
            data={"grant_type": "client_credentials"},
        )
        body = self._check(r)
        self._token = str(body["access_token"])
        self._expires = time.monotonic() + float(body["expires_in"])
        return self._token

    def _check(self, r: httpx.Response) -> JSON:
        if r.status_code >= 400:
            try:
                b = r.json()
            except ValueError:
                b = {}
            raise PayPalError(
                r.status_code,
                str(b.get("name") or b.get("error") or "ERROR"),
                str(b.get("message") or b.get("error_description") or r.text[:300]),
                b.get("debug_id"),
            )
        if not r.content:
            return {}
        data: JSON = r.json()
        return data

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}", **(extra or {})}

    def get(self, path: str) -> JSON:
        return self._check(self.http.get(path, headers=self._headers()))

    def post(self, path: str, request_id: str, json: JSON | None = None) -> JSON:
        headers = self._headers(
            {
                "PayPal-Request-Id": request_id,
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }
        )
        return self._check(self.http.post(path, json=json or {}, headers=headers))

    def post_multipart(
        self, path: str, request_id: str, files: dict[str, tuple[str, bytes, str]]
    ) -> JSON:
        headers = self._headers({"PayPal-Request-Id": request_id})
        return self._check(self.http.post(path, files=files, headers=headers))


@lru_cache
def get_client() -> PayPalClient:
    s = get_settings()
    return PayPalClient(s.paypal_base_url, s.paypal_client_id, s.paypal_client_secret)
