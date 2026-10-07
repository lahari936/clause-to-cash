from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://c2c:c2c@localhost:5432/c2c"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = SANDBOX_BASE
    paypal_webhook_id: str = ""
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if "sandbox" not in s.paypal_base_url:
        raise RuntimeError(f"Refusing non-sandbox PayPal URL: {s.paypal_base_url}")
    # Render hands out postgres:// URLs; SQLAlchemy needs the psycopg driver name.
    for prefix in ("postgres://", "postgresql://"):
        if s.database_url.startswith(prefix):
            s.database_url = "postgresql+psycopg://" + s.database_url[len(prefix) :]
    return s
