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
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (contracts, milestones, ledger, guard, disputes, copilot, webhooks):
    app.include_router(r.router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
