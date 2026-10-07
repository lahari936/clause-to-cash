# Clause-to-Cash

**The contract is the policy.** Upload a signed freelance or agency contract. AI agents extract the
terms with citations, a second agent checks every field against only its cited page, and once you
approve, those terms become a **Mandate**. Agents can then invoice, charge late fees and pay
subcontractors through PayPal, but only within the Mandate. Anything outside it is blocked and
logged, including prompt-injected requests.

> The LLM proposes, the Guard disposes. Amounts, payees, currencies and dates that move money come
> from the approved Mandate in Postgres, never from model output.

## Who it's for
Freelancers and small agencies who chase late payments, never enforce their own late-fee clauses,
and split revenue with subcontractors by hand.

## How it works

```
Contract PDF ─► Extractor agent ─► Validators + Checker agent ─► Human review ─► Mandate (frozen)
                 (cited JSON)       (sum checks, quote match,        (fix/confirm)        │
                                     context-starved verdicts)                            ▼
 Delivery ─► Acceptance agent ─► accept ─► guard.check() ─► PayPal Invoicing (clause in notes)
 Client pays ─► webhook / poll ─► ledger ─► guard.check() ×N ─► PayPal Payouts (exact shares)
 Overdue ─► Collections agent writes message ─► guard.check() ─► remind / late-fee invoice
 Dispute ─► Dispute agent builds evidence pack (PDF) ─► human approves ─► provide-evidence
 Copilot chat ─► tool calls ─► guard.check() ─► DENY + logged when outside the mandate
```

| Guard rule | Checks |
|---|---|
| G1 | Approved mandate exists |
| G2 | Payee is the mandate client / a mandate subcontractor |
| G3 | Currency matches |
| G4 | Milestone invoice = exact contracted amount, milestone accepted |
| G5 | Cumulative invoiced ≤ contract total |
| G6 | Late fee = deterministic `late_fee.compute()` (grace, cap) |
| G7 | Payout = exact share % of the paid amount, only after PAID |
| G8 | No duplicate action |
| G9 | Above threshold → human approval |
| G10 | Free-text (chat) requests must trace to a mandate rule |

## PayPal + AI

| PayPal API | Used for | Driven by |
|---|---|---|
| Invoicing v2 (create, send, remind, get) | Milestone invoices citing the contract clause; reminders; late-fee invoices | Acceptance + Collections agents, through the Guard |
| Payouts v1 | Revenue-share payouts to subcontractors, one batch per payment | Payment webhook, through the Guard |
| Webhooks (verify-webhook-signature) | `INVOICING.INVOICE.PAID`, payouts, disputes; verified, stored, deduped | Plus a 60s poll as backup |
| Disputes v1 (get, provide-evidence) | Evidence pack PDF built from clauses, deliveries and ledger | Dispute agent, human-approved |

LLM: Gemini 2.5 Flash on the free tier, called through `app/llm/provider.py` (Anthropic also supported).
If one model hits its quota, the next model in the list is used.

**Results** (`docs/PROGRESS.md`):
- Extraction field accuracy: **100%** on 8 synthetic contracts.
- Prompt injections blocked: **15/15** in the scripted suite and 15/15 with the real model.
- Tests: 107 passing.

### Compared with PayPal's Agent Toolkit / MCP server
Those tools give an agent PayPal access. Clause-to-Cash gives an agent *contract-bounded* access:
every money tool goes through `guard.check()` against the signed terms first.

## Sponsor tools
- **AG Grid** (community): ledger and guard-log grids.
- **Render**: one-click Blueprint (`render.yaml`) with API, static site and Postgres, all on free plans.
- Milestone timeline: built with CSS instead of Bryntum, since the Bryntum trial isn't free to ship.

## Run locally

```bash
cp .env.example .env               # sandbox app creds + 4 sandbox emails + GEMINI_API_KEY
docker compose up -d db
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # .venv/bin on macOS/Linux
.venv/Scripts/alembic upgrade head
.venv/Scripts/python scripts/seed_demo.py --offline
.venv/Scripts/uvicorn app.main:app --reload          # http://localhost:8000/health
cd ../frontend && npm install && npm run dev        # http://localhost:5173
```

Checks: `cd backend && pytest -q && ruff check . && mypy --strict app/guard app/paypal`.
Extraction eval: `python -m evals.run_eval --min-field-acc 0.90` (add `--cached` to reuse saved outputs).

## PayPal sandbox setup
1. Go to developer.paypal.com → Apps & Credentials (Sandbox) → Create App. Under **Features**, tick **Invoicing** and **Payouts**.
2. Go to Testing Tools → Sandbox Accounts. Use one **Business** account (the agency) and three **Personal** accounts (the client and two subcontractors). Put their emails in `.env`.
3. After deploying, go to the app → Webhooks → add `https://<api>.onrender.com/webhooks/paypal` for `INVOICING.INVOICE.*`, `PAYMENT.PAYOUTS*` and `CUSTOMER.DISPUTE.*`. Copy the Webhook ID into `PAYPAL_WEBHOOK_ID`.

Sandbox only: the code refuses to start if `PAYPAL_BASE_URL` isn't the sandbox host.

## Deploy (free)
Go to Render → New → **Blueprint** → select this repo, then fill in the secret env vars it asks for.
Render's free Postgres expires after 30 days. For a database that lasts, create a free
[Neon](https://neon.tech) Postgres and set its URL as `DATABASE_URL` on `c2c-api`.
Migrations run on start.

## License
MIT
