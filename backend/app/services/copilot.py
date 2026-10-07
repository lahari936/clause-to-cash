"""Executes copilot tool calls. Anything that moves money becomes a free_text Action and goes
through the guard; the model can propose numbers and payees but only mandate-exact ones pass."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import copilot as agent
from app.db.models import Clause, Contract, Invoice, Milestone
from app.guard import Action
from app.guard.engine import load_mandate
from app.money import dates, late_fee
from app.paypal.client import PayPalError
from app.services import milestones, payouts
from app.services.actions import execute
from app.services.invoicing import client_party

ACTOR = "copilot"


def context(db: Session, c: Contract) -> str:
    ms = db.scalars(select(Milestone).where(Milestone.contract_id == c.id).order_by(Milestone.seq))
    invs = db.scalars(select(Invoice).where(Invoice.contract_id == c.id))
    return (
        f"Contract {c.id} '{c.title}', currency {c.currency}, total {c.total_amount}.\n"
        + "".join(
            f"Milestone id={m.id} seq={m.seq} '{m.title}' {m.amount} status={m.status}\n"
            for m in ms
        )
        + "".join(
            f"Invoice id={i.id} kind={i.kind} {i.amount} status={i.status} due={i.due_date}\n"
            for i in invs
        )
    )


def _amount(s: str | None, default: Decimal) -> Decimal:
    if not s:
        return default
    try:
        return Decimal(re.sub(r"[^\d.\-]", "", s))
    except InvalidOperation:
        return Decimal(-1)  # unparseable -> guaranteed guard denial, never a silent default


def run_call(db: Session, c: Contract, call: agent.ToolCall) -> dict[str, Any]:
    assert c.currency
    client = client_party(db, c.id).paypal_email or ""
    t = call.tool
    if t == "list_milestones":
        ms = db.scalars(
            select(Milestone).where(Milestone.contract_id == c.id).order_by(Milestone.seq)
        )
        return {
            "milestones": [
                {
                    "id": m.id,
                    "seq": m.seq,
                    "title": m.title,
                    "amount": str(m.amount),
                    "status": m.status,
                }
                for m in ms
            ]
        }
    if t == "explain_clause":
        words = {w for w in re.findall(r"\w+", (call.query or "").lower()) if len(w) > 3}
        hits = [
            cl
            for cl in db.scalars(select(Clause).where(Clause.contract_id == c.id))
            if not words or words & set(re.findall(r"\w+", (cl.quote + " " + cl.kind).lower()))
        ]
        return {"clauses": [{"kind": h.kind, "page": h.page, "quote": h.quote} for h in hits[:5]]}
    if t == "mark_delivered":
        m = db.get(Milestone, call.milestone_id or -1)
        if not m or m.contract_id != c.id:
            return {"error": "unknown milestone"}
        d = milestones.deliver(db, m, call.note or "", [])
        return {"delivery_id": d.id, "acceptance": d.acceptance_json}

    # ---- money tools: always guarded, recipient defaults come from the mandate ----
    if t == "propose_invoice":
        m = db.get(Milestone, call.milestone_id) if call.milestone_id else None
        if m and m.contract_id != c.id:
            m = None
        a = Action(
            "milestone_invoice",
            c.id,
            _amount(call.amount, m.amount if m else Decimal(0)),
            c.currency,
            call.recipient or client,
            milestone_id=m.id if m else None,
            source="free_text",
            note=call.note or "",
        )
    elif t == "propose_late_fee":
        inv = db.get(Invoice, call.invoice_id) if call.invoice_id else None
        mv = load_mandate(db, c.id)
        fee = Decimal(0)
        if inv and inv.due_date and mv:
            fee = late_fee.compute(mv.late_fee, inv.amount, inv.due_date, dates.today())
        a = Action(
            "late_fee_invoice",
            c.id,
            _amount(call.amount, fee),
            c.currency,
            call.recipient or client,
            invoice_id=inv.id if inv else None,
            source="free_text",
        )
    elif t == "propose_payouts":
        inv = db.get(Invoice, call.invoice_id) if call.invoice_id else None
        if not inv or inv.contract_id != c.id:
            return {"error": "unknown invoice"}
        outs = payouts.pay_shares(db, inv, actor=ACTOR)
        return {"results": [o.to_json() for o in outs]}
    else:  # propose_payout: arbitrary payee/amount -> guard decides
        a = Action(
            "payout",
            c.id,
            _amount(call.amount, Decimal(0)),
            c.currency,
            call.recipient or "",
            invoice_id=call.invoice_id,
            source="free_text",
            note=call.note or "",
        )
    try:
        return execute(db, a, ACTOR).to_json()
    except PayPalError as e:
        return {"error": str(e)}


def chat(db: Session, c: Contract, message: str) -> dict[str, Any]:
    p = agent.plan(context(db, c), message)
    results = [
        {
            "tool": call.tool,
            "args": call.model_dump(exclude_none=True, exclude={"tool"}),
            "result": run_call(db, c, call),
        }
        for call in p.calls
    ]
    return {"reply": p.reply, "actions": results}
