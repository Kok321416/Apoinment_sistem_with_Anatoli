"""Smoke: async DB layer + slots compute (SQLite aiosqlite)."""
from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Consultant, Service, TimeSlot, User
from app.services.slots import get_available_slots_async


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_async_slots_sqlite(tmp_path):
    from app.models import Category

    db_path = tmp_path / "async_smoke.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        cat = Category(name_category="General")
        db.add(cat)
        await db.flush()
        user = User(username="u1", email="u1@example.com", password="x", is_active=True)
        db.add(user)
        await db.flush()
        consultant = Consultant(
            user_id=user.id,
            first_name="A",
            last_name="B",
            email="u1@example.com",
            category_of_specialist_id=cat.id,
        )
        db.add(consultant)
        await db.flush()
        calendar = Calendar(
            consultant_id=consultant.id,
            name="Main",
            is_active=True,
            book_ahead_hours=0,
            break_between_services_minutes=0,
        )
        db.add(calendar)
        await db.flush()
        service = Service(
            consultant_id=consultant.id,
            name="Consult",
            duration_minutes=60,
            is_active=True,
            price=0,
        )
        db.add(service)
        await db.flush()
        weekday = (date.today() + timedelta(days=7)).weekday()
        db.add(
            TimeSlot(
                calendar_id=calendar.id,
                day_of_week=weekday,
                start_time=time(9, 0),
                end_time=time(12, 0),
                is_available=True,
            )
        )
        await db.commit()

        await db.refresh(calendar)
        await db.refresh(service)
        result = await get_available_slots_async(db, calendar, service, date.today() + timedelta(days=7))
        assert "available_slots" in result
        assert isinstance(result["available_slots"], list)
        assert len(result["available_slots"]) > 0

    await engine.dispose()


@pytest.mark.smoke
def test_redis_health_without_url(monkeypatch):
    from app.config import get_settings
    from app.services import redis_client

    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()
    redis_client._client = None
    redis_client._client_failed = False
    h = redis_client.redis_health()
    assert h["configured"] is False
    assert h["mode"] == "memory"
