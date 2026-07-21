"""Smoke tests — no live DB required for pure helpers."""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def test_specialist_slug_for():
    from app.services.public_client import specialist_slug_for

    c = SimpleNamespace(id=42)
    assert specialist_slug_for(c) == "id-42"


def test_resolve_consultant_by_id_slug():
    from app.services.public_client import resolve_consultant_by_slug

    found = SimpleNamespace(id=7)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = found
    db.execute.side_effect = Exception("no public_slug column")

    assert resolve_consultant_by_slug(db, "id-7") is found


def test_delete_calendar_blocks_when_services():
    from app.services.entity_delete import delete_calendar

    db = MagicMock()
    db.query.return_value.filter.return_value.count.side_effect = [0, 2]  # bookings, services
    cal = SimpleNamespace(id=1)
    ok, msg = delete_calendar(db, cal)
    assert ok is False
    assert "услуг" in msg.lower()


def test_delete_calendar_blocks_when_bookings():
    from app.services.entity_delete import delete_calendar

    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 3
    cal = SimpleNamespace(id=1)
    ok, msg = delete_calendar(db, cal)
    assert ok is False
    assert "запис" in msg.lower()


def test_reminder_copy_uses_hours():
    from app.services.telegram import format_reminder_message, format_specialist_reminder_message

    booking = SimpleNamespace(
        booking_time=time(10, 0),
        booking_end_time=time(11, 0),
        booking_date=date.today() + timedelta(days=1),
        service=SimpleNamespace(name="Консультация", duration_minutes=60),
        calendar=SimpleNamespace(name="Основной", consultant=SimpleNamespace(first_name="Иван", last_name="Петров", email="a@b.c")),
        client_name="Клиент",
        client_phone="+7000",
        client_telegram="",
        client_email="",
    )
    msg = format_reminder_message(booking, 6)
    assert "6" in msg
    assert "24 часа" not in msg
    spec = format_specialist_reminder_message(booking, 6)
    assert "6" in spec


def test_bot_api_rejects_raw_token_when_secret_set(monkeypatch):
    from app.security import bot_api

    class S:
        bot_api_secret = "secret-value"
        telegram_bot_token = "bot-token"

    monkeypatch.setattr(bot_api, "get_settings", lambda: S())
    req = MagicMock()
    req.headers = {"X-Bot-Token": "bot-token"}
    assert bot_api.verify_bot_request(req, b"{}") is False


def test_health_endpoint():
    from app.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "schema" in body


def test_yandex_redirect_uri(monkeypatch):
    from app.services import yandex_auth

    class S:
        site_url = "https://example.com"

    monkeypatch.setattr(yandex_auth, "get_settings", lambda: S())
    assert yandex_auth.yandex_redirect_uri() == "https://example.com/accounts/yandex/callback/"


def test_yandex_authorize_url_contains_client_id(monkeypatch):
    from app.services import yandex_auth

    class S:
        yandex_oauth_client_id = "test-client-id"
        yandex_oauth_client_secret = "secret"
        site_url = "https://example.com"

    monkeypatch.setattr(yandex_auth, "get_settings", lambda: S())
    url = yandex_auth.build_authorize_url("state-token")
    assert "client_id=test-client-id" in url
    assert "state=state-token" in url
    assert "oauth.yandex.ru/authorize" in url


def test_normalize_phone_fits_db_column():
    from app.deps import normalize_phone

    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"
    assert len(normalize_phone("+7 (999) 123-45-67")) <= 15


def test_yandex_signup_creates_consultant():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401 — register metadata
    from app.database import Base
    from app.models import Consultant, SocialAccount, User
    from app.services.yandex_auth import complete_yandex_oauth

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    profile = {
        "id": 12345,
        "login": "testuser",
        "first_name": "Иван",
        "last_name": "Иванов",
        "display_name": "Иван Иванов",
        "default_email": "ivan@yandex.ru",
    }
    user, err = complete_yandex_oauth(
        db,
        process="signup",
        profile=profile,
        register_fio="Иванов Иван Петрович",
        register_phone="+7 (999) 123-45-67",
        connect_user_id=None,
    )
    assert err is None
    assert user is not None
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).one()
    assert consultant.phone == "+79991234567"
    assert len(consultant.phone) <= 15
    assert db.query(SocialAccount).filter(SocialAccount.provider == "yandex").count() == 1
    db.close()


def test_yandex_login_redirects_to_register_without_signup_data(monkeypatch):
    from app.main import app
    from app.routers import oauth as oauth_router

    monkeypatch.setattr(oauth_router, "yandex_oauth_configured", lambda: True)
    client = TestClient(app)
    r = client.get("/accounts/yandex/login/?process=signup", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/register/?error=yandex_signup"
