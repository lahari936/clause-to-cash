import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import contracts, copilot, disputes, guard, ledger, milestones, webhooks
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    sched = None
    if not get_settings().disable_scheduler:
        from app.jobs.scheduler import start

        sched = start()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="Clause-to-Cash", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Render's fromService gives a bare service name; accept "name", "host" or "https://host".
    allow_origins=[
        o if o.startswith("http") else f"https://{o if '.' in o else o + '.onrender.com'}"
        for o in (x.strip() for x in get_settings().cors_origins.split(","))
        if o
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (contracts, milestones, ledger, guard, disputes, copilot, webhooks):
    app.include_router(r.router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
