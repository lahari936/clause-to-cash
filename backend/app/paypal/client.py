"""Minimal typed PayPal REST client (sandbox only). Token cached until expiry.

Every POST requires a PayPal-Request-Id derived from the business action (milestone, invoice,
party), so any retry replays the same request instead of moving money twice.
"""

import time
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings

JSON = dict[str, Any]
SANDBOX_HOST = "api-m.sandbox.paypal.com"


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
        if urlparse(base_url).hostname != SANDBOX_HOST:
            raise RuntimeError(f"refusing non-sandbox PayPal URL {base_url}")
        self.http = http or httpx.Client(base_url=base_url, timeout=30)
        self.client_id = client_id
        self.secret = secret
        self._token: str | None = None
        self._expires = 0.0

    def token(self) -> str:
        if self._token and time.monotonic() < self._expires - 60:
            return self._token
        body = self._send(
            "POST",
            "/v1/oauth2/token",
            auth=(self.client_id, self.secret),
            data={"grant_type": "client_credentials"},
        )
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

    def _send(self, method: str, path: str, **kw: Any) -> JSON:
        try:
            return self._check(self.http.request(method, path, **kw))
        except httpx.HTTPError as e:  # timeouts etc: same handling as an API error
            raise PayPalError(0, "TRANSPORT", str(e) or type(e).__name__, None) from e

    def get(self, path: str) -> JSON:
        return self._send("GET", path, headers=self._headers())

    def post(
        self, path: str, request_id: str, json: JSON | None = None, prefer_full: bool = False
    ) -> JSON:
        extra = {"PayPal-Request-Id": request_id, "Content-Type": "application/json"}
        if prefer_full:  # only some endpoints (invoice create) accept it; others answer 406
            extra["Prefer"] = "return=representation"
        headers = self._headers(extra)
        return self._send("POST", path, json=json or {}, headers=headers)

    def post_multipart(
        self, path: str, request_id: str, files: dict[str, tuple[str, bytes, str]]
    ) -> JSON:
        headers = self._headers({"PayPal-Request-Id": request_id})
        return self._send("POST", path, files=files, headers=headers)


@lru_cache
def get_client() -> PayPalClient:
    s = get_settings()
    return PayPalClient(s.paypal_base_url, s.paypal_client_id, s.paypal_client_secret)
