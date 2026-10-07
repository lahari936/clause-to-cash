from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    assert TestClient(app).get("/health").json() == {"ok": True}


def test_live_paypal_url_refused(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PAYPAL_BASE_URL", "https://api-m.paypal.com")
    try:
        get_settings()
        raise AssertionError("live URL accepted")
    except RuntimeError:
        pass
    finally:
        get_settings.cache_clear()
