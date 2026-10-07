"""Collections agent: writes the polite message only.

Amounts and dates are passed in, never computed here."""

import logging

from pydantic import BaseModel

from app.llm.provider import structured

log = logging.getLogger(__name__)

PROMPT = """You write short, polite, firm payment reminders from a small agency to a client.
Use exactly the amounts, dates and clause text you are given; never change or add numbers.
Two to four sentences. No threats."""


class Message(BaseModel):
    subject: str
    body: str


def write(
    kind: str, client: str, invoice_ref: str, amount: str, due: str, clause: str, fee: str = ""
) -> Message:
    facts = (
        f"Kind: {kind}\nClient: {client}\nInvoice: {invoice_ref}\nAmount: {amount}\n"
        f"Due date: {due}\nLate fee now due (if any): {fee or 'none'}\nContract clause: {clause}"
    )
    try:
        return structured(facts, Message, system=PROMPT)
    except Exception:  # LLM down or out of quota: deterministic fallback, the action still runs
        log.warning("collections agent unavailable, using template")
        extra = f" Per the contract ({clause}), a late fee of {fee} now applies." if fee else ""
        return Message(
            subject=f"Reminder: invoice {invoice_ref} was due {due}",
            body=f"Hi {client}, a friendly reminder that invoice {invoice_ref} for {amount} "
            f"was due on {due}.{extra} Thank you!",
        )
