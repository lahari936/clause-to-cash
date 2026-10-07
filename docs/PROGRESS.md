# PROGRESS (file-based memory — read first every session)

Current phase: 0
Phase start tag: phase-0-start

## Done
- [x] 0.1 Repo scaffold (2026-10-07)
  - `cd backend && pytest -q && ruff check .` → 5 passed, 1 deselected (live); All checks passed
  - `cd frontend && npm run build` → built in 2.7s (React + Tailwind v4 + TanStack Query)
- [x] 0.2 Postgres + Alembic (2026-10-07)
  - `alembic upgrade head && alembic downgrade base && alembic upgrade head` → ok (15 tables, enums dropped on downgrade)
  - `pytest tests/test_db_smoke.py -q` → 2 passed (all tables exist; NUMERIC money round-trips as Decimal)
- [~] 0.4 LLM provider (2026-10-07) — offline part done, live call pending an API key
  - `pytest tests/test_llm_provider.py -q` → 3 passed (valid first try, error fed back once, gives up after 1 retry)
  - TODO: put real `ANTHROPIC_API_KEY` in `.env`, run `pytest -m live tests/test_llm_provider.py -q`

## In progress / blocked on user
- [ ] 0.3 PayPal sandbox setup — script ready: `cd backend && python scripts/paypal_check.py`. Needs sandbox REST app creds in `.env`.
- [ ] 0.5 Render deploy — `render.yaml` + `/health` ready. Needs Render account to create Blueprint from repo.
- [ ] Phase 0 checker review — run after 0.3 and 0.5 pass.

## Open questions
- Bryntum Gantt trial: request access early (needed in 2.6).

## Sandbox facts (no secrets here)
- Business (agency) account email:
- Client account email:
- Subcontractor A / B emails:
- Webhook id:

## Local dev notes
- Port 5432 on the dev laptop is taken by another Postgres; local `.env` uses 5433.
- Docker Desktop would not start from the agent shell, so local Postgres 16.2 runs from the `pgserver`
  wheel binaries (see DECISIONS). `docker compose up -d db` remains the documented path.
