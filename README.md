# Clause-to-Cash

Upload a signed freelance/agency contract. Agents extract the terms with citations, a checker verifies
each field, and the approved terms become a **Mandate**: the only policy under which agents may invoice,
charge late fees or pay subcontractors through PayPal (sandbox). The LLM proposes, the Guard disposes.

Status: Phase 0 (foundations). See [docs/PLAN.md](docs/PLAN.md) and [docs/PROGRESS.md](docs/PROGRESS.md).

## Run locally

```bash
cp .env.example .env            # fill in sandbox + Anthropic keys
docker compose up -d db
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # bin/ on macOS/Linux
alembic upgrade head && pytest -q
uvicorn app.main:app --reload   # http://localhost:8000/health
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

## License
MIT
