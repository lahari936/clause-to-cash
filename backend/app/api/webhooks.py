"""PayPal: verify -> store raw -> dedupe on event.id -> dispatch (idempotent handlers).
Unverified events are stored but never acted on; the poll job still catches real payments.
GitHub: HMAC-verified; merged PR labelled `milestone:<id>` records a delivery."""

import hashlib
import hmac
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Invoice, Milestone, Payout, WebhookEvent
from app.db.session import get_db
from app.paypal import disputes as pp_disputes
from app.paypal import webhooks as pp_webhooks
from app.paypal.client import PayPalError, get_client
from app.services import disputes, invoicing, milestones, payouts

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


def dispatch(db: Session, event: dict[str, Any]) -> str:
    etype = str(event.get("event_type", ""))
    res = event.get("resource") or {}
    if etype.startswith("INVOICING.INVOICE."):
        inv_id = res.get("id") or (res.get("invoice") or {}).get("id")
        inv = db.scalar(select(Invoice).where(Invoice.paypal_invoice_id == inv_id))
        return invoicing.sync_invoice(db, inv) if inv else "unknown invoice"
    if etype.startswith("PAYMENT.PAYOUTS"):
        batch = (res.get("batch_header") or {}).get("payout_batch_id") or res.get("payout_batch_id")
        if batch and db.scalar(select(Payout.id).where(Payout.paypal_batch_id == batch)):
            payouts.sync_batch(db, batch)
            return "payouts synced"
        return "unknown batch"
    if etype.startswith("CUSTOMER.DISPUTE."):
        dispute_id = str(res.get("dispute_id", ""))
        try:
            raw = pp_disputes.get(get_client(), dispute_id)
        except PayPalError:
            raw = res
        d = disputes.open_dispute(db, dispute_id, raw, dry_run=False)
        d.status = str(raw.get("status", d.status))
        return f"dispute {d.id}"
    return "ignored"


@router.post("/paypal")
async def paypal(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        event = json.loads(await request.body())
        event_id = str(event["id"])
    except (ValueError, KeyError) as e:
        raise HTTPException(400, "bad event") from e
    if db.get(WebhookEvent, event_id):
        return {"status": "duplicate"}
    try:
        verified = pp_webhooks.verify(
            get_client(), dict(request.headers), event, get_settings().paypal_webhook_id
        )
    except PayPalError as e:
        log.warning("webhook verify call failed: %s", e)
        verified = False
    ev = WebhookEvent(
        event_id=event_id, type=str(event.get("event_type", "")), raw_json=event, verified=verified
    )
    db.add(ev)
    db.commit()  # stored (and deduped) before processing
    if not verified:
        return {"status": "stored-unverified"}
    try:
        result = dispatch(db, event)
    except PayPalError as e:
        db.rollback()
        raise HTTPException(502, str(e)) from e  # PayPal retries delivery; handlers are idempotent
    ev.processed_at = datetime.now(UTC)
    db.commit()
    return {"status": result}


@router.post("/github")
async def github(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    body = await request.body()
    secret = get_settings().github_webhook_secret.encode()
    want = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(want, request.headers.get("x-hub-signature-256", "")):
        raise HTTPException(401, "bad signature")
    if request.headers.get("x-github-event") != "pull_request":
        return {"status": "ignored"}
    p = json.loads(body)
    pr = p.get("pull_request") or {}
    if p.get("action") != "closed" or not pr.get("merged"):
        return {"status": "ignored"}
    created = []
    for label in pr.get("labels", []):
        m = re.fullmatch(r"milestone:(\d+)", str(label.get("name", "")))
        ms = db.get(Milestone, int(m.group(1))) if m else None
        if ms is None:
            continue
        notes = f"PR #{pr.get('number')} merged: {pr.get('title', '')}\n\n{pr.get('body') or ''}"
        try:
            d = milestones.deliver(
                db, ms, notes[:10000], [str(pr.get("html_url", ""))], source="github"
            )
            created.append(d.id)
        except milestones.MilestoneError as e:
            log.info("github delivery skipped: %s", e)
    db.commit()
    return {"status": "ok", "deliveries": created}
