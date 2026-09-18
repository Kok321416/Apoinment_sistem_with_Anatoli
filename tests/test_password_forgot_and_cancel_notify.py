"""Cancel notify reliability + password forgot channels."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.passwords import hash_password
from app.database import Base
from app.models import (
    Booking,
    Calendar,
    Category,
    Consultant,
    NotifyOutbox,
    PasswordResetToken,
    Service,
    SocialAccount,
    User,
)
from app.services.password_reset import (
    GENERIC_OK,
    _yandex_email_for_user,
    request_password_reset,
)
from app.services.notify_outbox import enqueue_status_changed, process_notify_outbox
from app.db_schema import ensure_notify_outbox_schema


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def test_yandex_email_from_social_extra():
    db, _ = _session()
    u = User(
        username="ya@test.com",
        email="other@mail.ru",
        password=hash_password("x"),
        date_joined=datetime.utcnow(),
    )
    db.add(u)
    db.flush()
    db.add(
        SocialAccount(
            provider="yandex",
            uid="ya1",
            user_id=u.id,
            extra_data='{"default_email":"user@yandex.ru"}',
        )
    )
    db.commit()
    assert _yandex_email_for_user(db, u) == "user@yandex.ru"
    db.close()


def test_request_password_reset_telegram_sends(monkeypatch):
    db, _ = _session()
    u = User(
        username="+79001112233",
        email="",
        password=hash_password("oldpass12"),
        date_joined=datetime.utcnow(),
        is_active=True,
    )
    db.add(u)
    db.flush()
    db.add(SocialAccount(provider="telegram", uid="555001", user_id=u.id, extra_data="{}"))
    db.commit()

    sent = {}

    def _fake_send(chat_id, text, *a, **k):
        sent["chat_id"] = str(chat_id)
        sent["text"] = text
        return True

    monkeypatch.setattr("app.services.telegram._send_telegram", _fake_send)
    ok, msg = request_password_reset(db, login_raw="+79001112233", channel="telegram")
    assert ok
    assert msg == GENERIC_OK
    assert sent.get("chat_id") == "555001"
    assert "Сброс пароля" in sent.get("text", "")
    tok = db.query(PasswordResetToken).filter(PasswordResetToken.user_id == u.id).first()
    assert tok is not None
    db.close()


def test_request_password_reset_yandex_sends(monkeypatch):
    db, _ = _session()
    u = User(
        username="spec@yandex.ru",
        email="spec@yandex.ru",
        password=hash_password("oldpass12"),
        date_joined=datetime.utcnow(),
        is_active=True,
    )
    db.add(u)
    db.commit()
    sent = {}

    def _fake_mail(to_email, link):
        sent["email"] = to_email
        sent["link"] = link
        return True

    monkeypatch.setattr("app.services.email.send_password_reset_link_email", _fake_mail)
    ok, msg = request_password_reset(db, login_raw="spec@yandex.ru", channel="yandex")
    assert ok and msg == GENERIC_OK
    assert sent.get("email") == "spec@yandex.ru"
    assert "token=" in (sent.get("link") or "")
    db.close()


def test_notify_outbox_enqueue_and_process(monkeypatch):
    db, engine = _session()
    assert ensure_notify_outbox_schema(bind=engine)
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="a@t.c",
        phone="+7111",
        category_of_specialist_id=cat.id,
    )
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="C", color="#000")
    db.add(cal)
    db.flush()
    svc = Service(
        consultant_id=c.id,
        calendar_id=cal.id,
        name="Консультация",
        duration_minutes=60,
        price=1000,
        is_active=True,
    )
    db.add(svc)
    db.flush()
    b = Booking(
        calendar_id=cal.id,
        service_id=svc.id,
        client_name="Клиент",
        client_phone="+7222",
        booking_date=datetime.utcnow().date(),
        booking_time=datetime.utcnow().time().replace(microsecond=0),
        status="cancelled",
        cancel_reason="тест отмены",
        telegram_id=999001,
        source="specialist",
    )
    db.add(b)
    db.commit()

    oid = enqueue_status_changed(db, b.id, "confirmed")
    db.commit()
    assert oid
    called = {}

    def _fake_notify(sdb, booking, old_status=None):
        called["id"] = booking.id
        called["old"] = old_status

    monkeypatch.setattr("app.services.telegram.notify_booking_status_changed", _fake_notify)
    stats = process_notify_outbox(db)
    assert stats["done"] >= 1
    assert called.get("id") == b.id
    row = db.get(NotifyOutbox, oid)
    assert row.done_at is not None
    db.close()


def test_password_forgot_page_e2e(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.database import get_async_db
    from app.main import app

    monkeypatch.setattr(
        "app.services.password_reset.request_password_reset",
        lambda *a, **k: (True, GENERIC_OK),
    )

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def prep():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prep())

    async def override():
        async with sf() as s:
            yield s

    app.dependency_overrides[get_async_db] = override
    client = TestClient(app)
    try:
        r = client.get("/accounts/password/forgot/")
        assert r.status_code == 200
        assert "Восстановление пароля" in r.text
        assert 'value="telegram"' in r.text
        assert 'value="yandex"' in r.text
        login = client.get("/login/")
        assert "Забыли пароль?" in login.text
        import re

        tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        assert tok
        post = client.post(
            "/accounts/password/forgot/",
            data={
                "csrf_token": tok.group(1),
                "login": "nobody@example.com",
                "channel": "telegram",
            },
            follow_redirects=True,
        )
        assert post.status_code == 200
        assert "Если аккаунт найден" in post.text or GENERIC_OK.split(",")[0] in post.text
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
