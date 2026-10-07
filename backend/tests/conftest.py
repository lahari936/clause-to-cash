"""Test harness: separate c2c_test database, fake LLM, respx-mocked PayPal sandbox."""

import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

# --- environment must be set before app modules create the engine ---------------------------
from app.config import Settings  # noqa: E402

_main_url = Settings().database_url
for prefix in ("postgres://", "postgresql://"):
    if _main_url.startswith(prefix):
        _main_url = "postgresql+psycopg://" + _main_url[len(prefix) :]
TEST_URL = _main_url.rsplit("/", 1)[0] + "/c2c_test"
os.environ.update(
    DATABASE_URL=TEST_URL,
    DISABLE_SCHEDULER="true",
    PAYPAL_CLIENT_ID="test-id",
    PAYPAL_CLIENT_SECRET="test-secret",
    PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com",
    PAYPAL_WEBHOOK_ID="WH-TEST",
    AGENCY_EMAIL="agency@test.example",
    CLIENT_EMAIL="client@test.example",
    SUB_A_EMAIL="ana@test.example",
    SUB_B_EMAIL="ben@test.example",
    APPROVAL_THRESHOLD="5000.00",
    GITHUB_WEBHOOK_SECRET="gh-secret",
    DEMO_CLOCK="",
)

import respx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


def _ensure_db() -> None:
    eng = create_engine(_main_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='c2c_test'")):
            conn.execute(text("CREATE DATABASE c2c_test"))
    eng.dispose()


_ensure_db()

from app.db.models import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.money import dates  # noqa: E402
from app.paypal.client import get_client  # noqa: E402

ROOT = Path(__file__).parents[1]
SANDBOX = "https://api-m.sandbox.paypal.com"
GOLD = ROOT / "evals" / "gold"
PDFS = ROOT / "evals" / "contracts"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:  # enum types survive drop_all; drop them too
        for (name,) in conn.execute(text("SELECT typname FROM pg_type WHERE typtype='e'")):
            conn.execute(text(f'DROP TYPE IF EXISTS "{name}" CASCADE'))
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db() -> Iterator[Any]:
    with SessionLocal() as s:
        yield s
        s.rollback()
    tables = ", ".join(f'"{t}"' for t in Base.metadata.tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _reset(request: pytest.FixtureRequest) -> Iterator[None]:
    get_client.cache_clear()
    dates.set_today(None)
    yield
    dates.set_today(None)


# --- fake LLM ---------------------------------------------------------------------------------
Responder = Callable[[str], dict[str, Any]]


class FakeLLM:
    """Routes structured() calls by schema name. Unregistered schemas raise (no live calls)."""

    def __init__(self) -> None:
        self.routes: dict[str, Responder] = {}
        self.calls: list[tuple[str, str]] = []

    def on(self, schema: str, fn: Responder | dict[str, Any]) -> None:
        self.routes[schema] = fn if callable(fn) else (lambda _p, v=fn: v)

    def __call__(self, system: str, messages: list[dict[str, Any]], tool: dict[str, Any]) -> Any:
        name = tool["description"].removeprefix("Submit the ").removesuffix(" result.")
        prompt = messages[0]["content"]
        self.calls.append((name, prompt))
        if name not in self.routes:
            raise RuntimeError(f"no fake LLM route for {name}")
        return "fake", self.routes[name](prompt)


@pytest.fixture(autouse=True)
def llm(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    fake = FakeLLM()
    if "live" not in request.keywords:
        monkeypatch.setattr("app.llm.provider._caller", lambda: fake)
    return fake


def ok_verdicts(prompt: str) -> dict[str, Any]:
    paths = [line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("path: ")]
    return {"results": [{"path": p, "verdict": "ok", "reason": "matches page"} for p in paths]}


def gold(slug: str = "01_northwind_web") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((GOLD / f"{slug}.json").read_text())
    return data


# --- PayPal sandbox mock ----------------------------------------------------------------------
@pytest.fixture
def pp() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=SANDBOX, assert_all_called=False) as router:
        router.post("/v1/oauth2/token").respond(
            json={"access_token": "A21-test", "expires_in": 32400, "token_type": "Bearer"}
        )
        yield router


def mock_invoicing(pp: respx.MockRouter) -> None:
    counter = iter(range(1, 1000))

    def create(request: Any) -> Any:
        import httpx

        return httpx.Response(201, json={"id": f"INV2-TEST-{next(counter):04d}", "status": "DRAFT"})

    pp.post("/v2/invoicing/invoices").mock(side_effect=create)
    pp.post(url__regex=r".*/v2/invoicing/invoices/[^/]+/send").respond(200, json={})
    pp.post(url__regex=r".*/v2/invoicing/invoices/[^/]+/remind").respond(204)
    pp.post("/v1/payments/payouts").respond(
        201, json={"batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "PENDING"}}
    )


# --- domain helpers ---------------------------------------------------------------------------
def approved_contract(db: Any, llm: FakeLLM, slug: str = "01_northwind_web", **kw: Any) -> Any:
    """Upload + extract (fake LLM returns gold) + approve. Returns the Contract."""
    from app.services import contracts

    c = contracts.upload(db, "Website Redesign", (PDFS / f"{slug}.pdf").read_bytes())
    llm.on("ContractExtraction", gold(slug))
    llm.on("CheckBatch", ok_verdicts)
    contracts.run_extraction(db, c)
    contracts.approve(db, c, "owner@agency", **kw)
    db.commit()
    return c
