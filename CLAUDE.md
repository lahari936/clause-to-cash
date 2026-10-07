# Clause-to-Cash — Claude Code operating rules

Clause-to-Cash turns a freelance/agency contract PDF into enforced PayPal money movement.
An extraction agent reads the contract, a checker verifies every field against the cited clause,
and the approved terms become a **Mandate**: the only policy under which any agent may invoice,
charge late fees, or pay subcontractors through PayPal.

Core principle: **the LLM proposes, the Guard disposes.** No amount, payee, currency or date that
moves money ever comes from model output directly. It comes from the approved Mandate in Postgres,
and every money-moving call passes `guard.check()` first.

Hackathon: PayPal AI Hackathon (Devpost). Deadline Nov 12, 2026 12:00 PM PST (Nov 13, 1:30 AM IST).
Internal target: submission complete by **Nov 11 IST**.

## Session start (every session, no exceptions)
1. Read `docs/PROGRESS.md` (file-based memory — the source of truth for what is done).
2. Read the current phase in `docs/PLAN.md`.
3. Pick the FIRST unchecked task in the current phase. Work on one task at a time.

## Definition of done (command-proven progress)
- Every task in PLAN.md has an **Acceptance** command. A task is done only when that command
  has been run in this session and passed. Paste the command + a 1–3 line result summary into
  `docs/PROGRESS.md` under the task.
- Never mark a task done based on "the code looks right".
- At the end of each phase, invoke the `checker` subagent (`.claude/agents/checker.md`) on the
  phase diff. Fix every BLOCKER it reports before starting the next phase.
- Record any non-obvious choice (library, schema change, API workaround) in `docs/DECISIONS.md`
  as: date, decision, reason, alternative rejected.

## Stack (do not change without a DECISIONS.md entry)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Postgres 16, httpx, pydantic v2, APScheduler
- PDF: PyMuPDF (`pymupdf`) for text + page numbers
- LLM: Anthropic SDK, model from env `LLM_MODEL` (default `claude-sonnet-5-5`); structured output via
  tool use with pydantic-derived JSON schemas. Provider is behind `app/llm/provider.py` so Gemini
  can be swapped in via `LLM_PROVIDER=gemini`.
- PayPal: REST APIs, sandbox only (`https://api-m.sandbox.paypal.com`). Own typed client in
  `app/paypal/`. Never call PayPal from route handlers directly — go through services + guard.
- Frontend: React 18 + Vite + TypeScript, TanStack Query, Tailwind, AG Grid (community),
  Bryntum Gantt (trial), PayPal JS SDK v6 only if a pay-button flow is added.
- Hosting: Render (web service + static site + Postgres) via `render.yaml`.
- Tests: pytest (+ respx for mocking PayPal HTTP), vitest for frontend utilities.

## Hard rules
- Secrets only in `.env` (gitignored). `.env.example` lists every key with a dummy value.
- Sandbox credentials only. If code ever points at `api-m.paypal.com` (live), stop and flag it.
- All PayPal POSTs send a `PayPal-Request-Id` header (idempotency) derived from our DB row id.
- Webhooks: verify signature via `/v1/notifications/verify-webhook-signature`, store raw event in
  `webhook_events`, dedupe on `event.id`, process idempotently.
- Money is `Decimal` in Python and `NUMERIC(12,2)` in Postgres. Never float.
- Late-fee math, due dates and split amounts are deterministic Python functions with unit tests.
  The LLM may explain them, never compute them.
- Every extracted field stores `source_page`, `source_quote` (≤ 300 chars) and `confidence`.
- Guard denials are not errors to "work around". If a test fails because the guard blocked
  something, the fix is in the data or the rule, never a bypass flag.
- Keep functions small and typed. `ruff` + `mypy --strict app/guard app/paypal` must pass.

## Commands
- Backend dev: `cd backend && uvicorn app.main:app --reload`
- Migrations: `cd backend && alembic upgrade head`
- Backend tests: `cd backend && pytest -q`
- Lint/type: `cd backend && ruff check . && mypy --strict app/guard app/paypal`
- Extraction eval: `cd backend && python -m evals.run_eval --min-field-acc 0.90`
- Frontend dev: `cd frontend && npm run dev`
- Frontend build: `cd frontend && npm run build`
- Public webhook URL in dev: `cloudflared tunnel --url http://localhost:8000`

## Style
- Small commits, message format `phase-N: <task id> <summary>`.
- If a task is ambiguous, write the question into PROGRESS.md under "Open questions" and pick
  the simplest option that keeps the demo path working. Do not stall.
