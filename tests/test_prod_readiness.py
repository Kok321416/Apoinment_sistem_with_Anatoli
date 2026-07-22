"""Production readiness checks."""
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.services.prod_readiness import format_readiness_report, run_prod_readiness


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _FakeSettings:
    secret_key = "long-enough-secret-key-for-test"
    debug = False
    telegram_bot_token = "123:abc"
    bot_api_secret = "bot-secret"
    notify_dedup = True
    smtp_host = "smtp.test"
    smtp_user = "u"
    smtp_password = "p"
    site_url = "https://example.com"
    platform_admin_enabled = True


def test_prod_readiness_passes_with_good_config():
    db = _session()
    with patch("app.services.prod_readiness.get_settings", return_value=_FakeSettings()):
        with patch("app.services.prod_readiness.get_schema_health", return_value={"ready": True, "degraded": False}):
            data = run_prod_readiness(db, _FakeSettings())
    assert data["ok"] is True
    assert data["fail_count"] == 0
    report = format_readiness_report(data)
    assert "PASS" in report
    db.close()


def test_prod_readiness_fails_without_telegram():
    db = _session()
    bad = _FakeSettings()
    bad.telegram_bot_token = ""
    data = run_prod_readiness(db, bad)
    assert data["ok"] is False
    assert any(c["id"] == "telegram_bot" and c["level"] == "fail" for c in data["checks"])
    db.close()
