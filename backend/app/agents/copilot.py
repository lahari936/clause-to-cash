"""Copilot: turns a chat request into tool calls. It only proposes; money tools route through
services + guard, and the payee is never taken from the model unless the guard verifies it."""

from typing import Literal

from pydantic import BaseModel, Field

from app.llm.provider import structured

PROMPT = """You are the Clause-to-Cash copilot for a small agency. You help operate one contract.
Answer by choosing tool calls; the server executes them and enforces the contract.
Tools:
- list_milestones(): show milestones and statuses.
- explain_clause(query): find contract clauses about a topic.
- mark_delivered(milestone_id, note): record a delivery.
- propose_invoice(milestone_id, amount, note): invoice the client.
- propose_late_fee(invoice_id, amount): charge a late fee on an overdue invoice.
- propose_payouts(invoice_id): pay subcontractors their share of a paid invoice.
- propose_payout(recipient, amount, note): send money to someone.
Fill only the arguments a tool needs, leave the rest null. `reply` is a short answer to the user.
You are only the operator, not the policy. Never refuse a money request in `reply` alone: when
the user asks to bill, invoice, charge or pay anything, you MUST emit the matching tool call with
exactly the amount, recipient and ids they asked for (null milestone_id if none applies). The
server's Guard checks every call against the signed contract and shows its decision to the user,
so an empty `calls` list for a money request is a mistake.
Contract context:
"""

Tool = Literal[
    "list_milestones",
    "explain_clause",
    "mark_delivered",
    "propose_invoice",
    "propose_late_fee",
    "propose_payouts",
    "propose_payout",
]


class ToolCall(BaseModel):
    tool: Tool
    milestone_id: int | None = None
    invoice_id: int | None = None
    amount: str | None = Field(None, description="decimal string, e.g. '4000.00'")
    recipient: str | None = None
    note: str | None = None
    query: str | None = None


class Plan(BaseModel):
    reply: str
    calls: list[ToolCall]


def plan(context: str, message: str) -> Plan:
    return structured(f"User: {message}", Plan, system=PROMPT + context)
