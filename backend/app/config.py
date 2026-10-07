from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
REPO_ENV = Path(__file__).resolve().parents[2] / ".env"  # works from any cwd


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ENV, extra="ignore")

    database_url: str = "postgresql+psycopg://c2c:c2c@localhost:5432/c2c"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = SANDBOX_BASE
    paypal_webhook_id: str = ""
    llm_provider: str = "gemini"
    # Comma list: on quota errors the next free-tier model is tried.
    llm_model: str = (
        "gemini-2.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite,"
        "gemini-3.5-flash,gemini-flash-latest"
    )
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    cors_origins: str = "http://localhost:5173"
    # Sandbox accounts the approved mandate maps contract parties onto.
    agency_email: str = ""
    client_email: str = ""
    sub_a_email: str = ""
    sub_b_email: str = ""
    approval_threshold: Decimal = Decimal("5000.00")
    demo_clock: str = ""
    github_webhook_secret: str = ""
    disable_scheduler: bool = False
    allow_demo_clock: bool = True  # set false to stop anyone fast-forwarding late fees


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if urlparse(s.paypal_base_url).hostname != "api-m.sandbox.paypal.com":
        raise RuntimeError(f"Refusing non-sandbox PayPal URL: {s.paypal_base_url}")
    # Render hands out postgres:// URLs; SQLAlchemy needs the psycopg driver name.
    for prefix in ("postgres://", "postgresql://"):
        if s.database_url.startswith(prefix):
            s.database_url = "postgresql+psycopg://" + s.database_url[len(prefix) :]
    return s
