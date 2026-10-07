import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Delivery, Milestone
from app.main import app
from tests.conftest import approved_contract

api = TestClient(app)


def _post(payload: dict, secret: bytes = b"gh-secret", event: str = "pull_request"):  # type: ignore[no-untyped-def,type-arg]
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return api.post(
        "/webhooks/github",
        content=body,
        headers={"x-hub-signature-256": sig, "x-github-event": event},
    )


def _pr(mid: int, merged: bool = True) -> dict:  # type: ignore[type-arg]
    return {
        "action": "closed",
        "pull_request": {
            "number": 42,
            "merged": merged,
            "title": "Storefront on staging",
            "body": "Lighthouse 91",
            "html_url": "https://github.com/acme/site/pull/42",
            "labels": [{"name": f"milestone:{mid}"}, {"name": "frontend"}],
        },
    }


def test_merged_pr_creates_delivery(db, llm) -> None:  # type: ignore[no-untyped-def]
    c = approved_contract(db, llm)
    llm.on("AcceptanceResult", {"meets_criteria": True, "gaps": [], "summary_for_client": "ok"})
    m = db.scalars(select(Milestone).where(Milestone.contract_id == c.id, Milestone.seq == 2)).one()
    r = _post(_pr(m.id))
    assert r.status_code == 200 and len(r.json()["deliveries"]) == 1
    d = db.scalars(select(Delivery)).one()
    assert d.source == "github" and d.links == ["https://github.com/acme/site/pull/42"]
    assert "Lighthouse 91" in d.notes
    db.expire_all()
    assert db.get(Milestone, m.id).status == "delivered"


def test_bad_signature_rejected(db) -> None:  # type: ignore[no-untyped-def]
    assert _post(_pr(1), secret=b"wrong").status_code == 401


def test_unmerged_or_other_events_ignored(db) -> None:  # type: ignore[no-untyped-def]
    assert _post(_pr(1, merged=False)).json() == {"status": "ignored"}
    assert _post(_pr(1), event="push").json() == {"status": "ignored"}
