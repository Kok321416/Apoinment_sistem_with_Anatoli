"""Specialist Telegram inline booking actions (confirm via bot API)."""
from __future__ import annotations

import asyncio
import json
from datetime import date, time
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_async_db
from app.main import app
from app.models import Booking, Calendar, Category, Consultant, Integration, Service


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


async def _seed(session_factory, *, specialist_chat: str, booking_status: str = "pending"):
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
            name="S",
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
            booking_date=date.today(),
            booking_time=time(10, 0),
            booking_end_time=time(11, 0),
            client_name="Client",
            client_phone="+7999",
            status=booking_status,
        )
        db.add(booking)
        await db.commit()
        return booking.id, consultant.id


def test_specialist_booking_confirm_success():
    engine, sf, client = _async_test_client()
    try:
        booking_id, _ = asyncio.run(_seed(sf, specialist_chat="900111"))
        with patch("app.routers.api.verify_bot_request", return_value=True):
            r = client.post(
                "/api/telegram/specialist-booking-confirm",
                content=json.dumps({"telegram_chat_id": "900111", "booking_id": booking_id}),
                headers={"Content-Type": "application/json"},
            )
        assert r.status_code == 200
        assert r.json()["success"] is True
    finally:
        _close_async_test_client(engine)


def test_specialist_booking_confirm_idor_other_consultant():
    engine, sf, client = _async_test_client()
    try:
        booking_id, _ = asyncio.run(_seed(sf, specialist_chat="900111"))

        async def _other_integration():
            async with sf() as db:
                cat = Category(name_category="X")
                db.add(cat)
                await db.flush()
                other = Consultant(
                    first_name="B",
                    last_name="B",
                    email="other@t.c",
                    phone="+7888",
                    category_of_specialist_id=cat.id,
                )
                db.add(other)
                await db.flush()
                db.add(
                    Integration(
                        consultant_id=other.id,
                        telegram_connected=True,
                        telegram_enabled=True,
                        telegram_chat_id="800222",
                    )
                )
                await db.commit()

        asyncio.run(_other_integration())

        with patch("app.routers.api.verify_bot_request", return_value=True):
            r = client.post(
                "/api/telegram/specialist-booking-confirm",
                content=json.dumps({"telegram_chat_id": "800222", "booking_id": booking_id}),
                headers={"Content-Type": "application/json"},
            )
        body = r.json()
        assert body["success"] is False
        assert body["error"] == "booking not found"
    finally:
        _close_async_test_client(engine)


def test_specialist_booking_confirm_rejects_completed():
    engine, sf, client = _async_test_client()
    try:
        booking_id, _ = asyncio.run(_seed(sf, specialist_chat="900111", booking_status="completed"))
        with patch("app.routers.api.verify_bot_request", return_value=True):
            r = client.post(
                "/api/telegram/specialist-booking-confirm",
                content=json.dumps({"telegram_chat_id": "900111", "booking_id": booking_id}),
                headers={"Content-Type": "application/json"},
            )
        body = r.json()
        assert body["success"] is False
        assert body["error"] == "booking not confirmable"
    finally:
        _close_async_test_client(engine)
