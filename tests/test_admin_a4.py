"""Admin A4: email log, analytics, settings, activity."""
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import EmailDeliveryLog, PlatformUserActivity, User
from app.services.platform_activity import record_user_activity
from app.services.platform_admin_analytics import analytics_snapshot
from app.services.platform_admin_settings import integration_status, mask_secret, platform_flags
from app.services.platform_email_log import list_email_deliveries, log_email_delivery, resend_email_delivery


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("abc") == "***"
    assert mask_secret("1234567890") == "1234...7890"


def test_integration_status_and_flags():
    snap = integration_status()
    assert "smtp" in snap and "telegram" in snap
    flags = platform_flags()
    keys = {f["key"] for f in flags}
    assert "PLATFORM_ADMIN_ENABLED" in keys
    assert "SECRET_KEY" in keys


def test_email_log_and_resend(monkeypatch):
    db = _session()
    row = log_email_delivery(
        db,
        to_email="a@t.c",
        subject="Test",
        status="sent",
        html_body="<p>hi</p>",
        text_body="hi",
        template_key="test",
    )
    assert row.id
    listed = list_email_deliveries(db, q="a@t.c")
    assert any(e.id == row.id for e in listed)

    monkeypatch.setattr(
        "app.services.email.send_email",
        lambda *a, **k: True,
    )
    resent, err = resend_email_delivery(db, row.id)
    assert err is None
    assert resent is not None
    db.close()


def test_activity_and_analytics_dau():
    db = _session()
    u = User(username="u@t.c", password="x", email="u@t.c", date_joined=datetime.now())
    db.add(u)
    db.commit()
    record_user_activity(db, u.id)
    db.commit()
    assert (
        db.query(PlatformUserActivity)
        .filter(PlatformUserActivity.user_id == u.id, PlatformUserActivity.activity_date == date.today())
        .count()
        == 1
    )
    record_user_activity(db, u.id)
    db.commit()
    assert (
        db.query(PlatformUserActivity)
        .filter(PlatformUserActivity.user_id == u.id, PlatformUserActivity.activity_date == date.today())
        .count()
        == 1
    )
    metrics = analytics_snapshot(db)
    assert metrics["dau"] >= 1
    assert len(metrics["daily_active"]) == 7
    db.close()


def test_login_user_records_activity():
    from app.auth.session import login_user
    from starlette.requests import Request

    db = _session()
    u = User(username="login@t.c", password="x", email="login@t.c", date_joined=datetime.now())
    db.add(u)
    db.commit()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "headers": [],
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
        "scheme": "http",
        "session": {},
    }
    request = Request(scope)
    login_user(request, u, db)
    db.refresh(u)
    assert u.last_login is not None
    assert (
        db.query(PlatformUserActivity)
        .filter(PlatformUserActivity.user_id == u.id, PlatformUserActivity.activity_date == date.today())
        .count()
        == 1
    )
    db.close()
