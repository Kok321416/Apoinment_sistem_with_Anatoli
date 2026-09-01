"""Specialist booking cancel with reason (Telegram + site)."""
from __future__ import annotations

import asyncio
import json
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_async_db
from app.main import app
from app.models import Booking, Calendar, Category, Consultant, Integration, Service
from app.services import telegram as tg
from app.services.telegram_copy import format_booking_cancelled_client, format_booking_status_changed_client


def _async_test_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare_schema())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db
    return engine, session_factory, TestClient(app)


def _close_async_test_client(engine):
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _seed(session_factory, *, specialist_chat: str, booking_status: str = "confirmed"):
    async with session_factory() as db:
        cat = Category(name_category="Общая")
        db.add(cat)
        await db.flush()
        consultant = Consultant(
            first_name="Spec",
            last_name="A",
            email="spec@t.c",
            phone="+7999",
            category_of_specialist_id=cat.id,
        )
        db.add(consultant)
        await db.flush()
        cal = Calendar(consultant_id=consultant.id, name="Cal", color="#000")
        db.add(cal)
        await db.flush()
        svc = Service(
            consultant_id=consultant.id,
            calendar_id=cal.id,
            name="Консультация 325 кабинет",
            duration_minutes=60,
            is_active=True,
        )
        db.add(svc)
        await db.flush()
        db.add(
            Integration(
                consultant_id=consultant.id,
                telegram_connected=True,
                telegram_enabled=True,
                telegram_chat_id=specialist_chat,
            )
        )
        booking = Booking(
            service_id=svc.id,
            calendar_id=cal.id,
            booking_date=date(2026, 9, 2),
            booking_time=time(10, 0),
            booking_end_time=time(11, 0),
            client_name="Вероника Мельникова",
            client_phone="+79087780378",
            client_telegram="mememelolik",
            status=booking_status,
        )
        db.add(booking)
        await db.commit()
        return booking.id


def test_format_booking_cancelled_client_message():
    booking = SimpleNamespace(
        client_name="Вероника Мельникова",
        client_phone="+79087780378",
        client_telegram="mememelolik",
        client_email=None,
        service=SimpleNamespace(name="Консультация 325 кабинет", duration_minutes=60),
        booking_date=date(2026, 9, 2),
        booking_time=time(10, 0),
        booking_end_time=time(11, 0),
        calendar=SimpleNamespace(
            name="Кабинет",
            consultant=SimpleNamespace(first_name="Иван", last_name="П", email="a@b.c"),
        ),
        cancel_reason="занят другой клиент",
    )
    text = format_booking_cancelled_client(booking, "confirmed", "занят другой клиент")
    assert "Упс, консультация отменена" in text
    assert "занят другой клиент" in text
    assert "Вероника Мельникова" in text
    assert "Подтверждена" in text
    assert "Отменена" in text
    assert "10:00" in text
    assert "+79087780378" in text
    assert "mememelolik" in text


def test_status_changed_client_uses_cancel_template_with_reason():
    booking = SimpleNamespace(
        client_name="Анна",
        client_phone="+7999",
        client_telegram="",
        client_email=None,
        service=SimpleNamespace(name="Консультация", duration_minutes=60),
        booking_date=date(2026, 9, 2),
        booking_time=time(10, 0),
        booking_end_time=time(11, 0),
        calendar=SimpleNamespace(
            name="Кабинет",
            consultant=SimpleNamespace(first_name="Иван", last_name="", email=""),
        ),
        cancel_reason="болею",
    )
    text = format_booking_status_changed_client(booking, "cancelled", "confirmed")
    assert "Упс, консультация отменена" in text
    assert "болею" in text


def test_specialist_booking_cancel_api_success():
    engine, sf, client = _async_test_client()
    try:
        booking_id = asyncio.run(_seed(sf, specialist_chat="900111"))
        with patch("app.routers.api.verify_bot_request", return_value=True):
            r = client.post(
                "/api/telegram/specialist-booking-cancel",
                content=json.dumps(
                    {
                        "telegram_chat_id": "900111",
                        "booking_id": booking_id,
                        "reason": "не смогу в это время",
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True

        async def _check():
            async with sf() as db:
                booking = (await db.execute(select(Booking).where(Booking.id == booking_id))).scalar_one()
                assert booking.status == "cancelled"
                assert booking.cancel_reason == "не смогу в это время"

        asyncio.run(_check())
    finally:
        _close_async_test_client(engine)


def test_specialist_booking_cancel_requires_reason():
    engine, sf, client = _async_test_client()
    try:
        booking_id = asyncio.run(_seed(sf, specialist_chat="900111"))
        with patch("app.routers.api.verify_bot_request", return_value=True):
            r = client.post(
                "/api/telegram/specialist-booking-cancel",
                content=json.dumps(
                    {"telegram_chat_id": "900111", "booking_id": booking_id, "reason": "  "}
                ),
                headers={"Content-Type": "application/json"},
            )
        body = r.json()
        assert body["success"] is False
    finally:
        _close_async_test_client(engine)


def test_specialist_new_booking_keyboard_includes_cancel(monkeypatch):
    monkeypatch.setattr(tg.settings, "site_url", "https://example.com")
    kb = tg.specialist_new_booking_inline_keyboard(7)
    assert kb["inline_keyboard"][2][0] == {
        "text": "❌ Отменить",
        "callback_data": "spec_book_cancel_7",
    }


def test_specialist_keyboard_after_confirm_includes_cancel(monkeypatch):
    monkeypatch.setattr(tg.settings, "site_url", "https://example.com")
    kb = tg.specialist_new_booking_keyboard_after_confirm(9)
    assert len(kb["inline_keyboard"]) == 2
    assert kb["inline_keyboard"][1][0]["callback_data"] == "spec_book_cancel_9"
