"""Smoke: async calendar schedule helpers + page_context_async."""
from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.database import Base
from app.models import Calendar, Category, Consultant, TimeSlot, User
from app.services.calendar_schedule import (
    build_schedule_payload,
    clear_day_slots_async,
    copy_day_slots_async,
    slots_by_day_async,
)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_async_schedule_helpers_sqlite(tmp_path):
    db_path = tmp_path / "schedule_async.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        cat = Category(name_category="General")
        db.add(cat)
        await db.flush()
        user = User(username="sched1", email="s1@example.com", password="x", is_active=True)
        db.add(user)
        await db.flush()
        consultant = Consultant(
            user_id=user.id,
            first_name="A",
            last_name="B",
            email="s1@example.com",
            category_of_specialist_id=cat.id,
        )
        db.add(consultant)
        await db.flush()
        calendar = Calendar(
            consultant_id=consultant.id,
            name="Main",
            is_active=True,
            color="#000",
        )
        db.add(calendar)
        await db.flush()
        db.add(
            TimeSlot(
                calendar_id=calendar.id,
                day_of_week=0,
                start_time=time(10, 0),
                end_time=time(12, 0),
                is_available=True,
            )
        )
        await db.commit()

        grouped = await slots_by_day_async(db, calendar.id)
        assert len(grouped[0]) == 1
        payload = build_schedule_payload(calendar, grouped)
        assert payload["week"][0]["slots"][0]["start"] == "10:00"

        created = await copy_day_slots_async(db, calendar, 0, [1, 2], replace=True)
        assert created == 2
        await db.commit()
        grouped2 = await slots_by_day_async(db, calendar.id)
        assert len(grouped2[1]) == 1 and len(grouped2[2]) == 1

        removed = await clear_day_slots_async(db, calendar.id, 1)
        assert removed == 1
        await db.commit()

        from app.services.calendars_hub import build_calendars_payload_async
        from app.services.entity_delete import delete_calendar_async

        hub = await build_calendars_payload_async(db, [calendar], "https://example.test/s/x/")
        assert hub["dashboard"]["total"] == 1
        assert hub["calendars"][0]["time_slots_count"] >= 1

        ok, msg = await delete_calendar_async(db, calendar)
        assert ok is True
        assert "удален" in msg.lower() or "удалён" in msg.lower() or msg

    await engine.dispose()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_async_crm_and_profile_helpers_sqlite(tmp_path):
    from app.models import ClientCard
    from app.services.clients_crm import build_crm_payload_async
    from app.services.profile_hub import build_profile_payload_async, completeness_async

    db_path = tmp_path / "crm_async.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        cat = Category(name_category="General")
        db.add(cat)
        await db.flush()
        user = User(username="crm1", email="c1@example.com", password="x", is_active=True)
        db.add(user)
        await db.flush()
        consultant = Consultant(
            user_id=user.id,
            first_name="A",
            last_name="B",
            email="c1@example.com",
            category_of_specialist_id=cat.id,
        )
        db.add(consultant)
        await db.flush()
        card = ClientCard(consultant_id=consultant.id, name="Client", phone="+7000")
        db.add(card)
        await db.commit()

        crm = await build_crm_payload_async(db, consultant.id, [card])
        assert crm["dashboard"]["total"] == 1
        assert crm["clients"][0]["name"] == "Client"

        comp = await completeness_async(consultant, db, consultant.id)
        assert "percent" in comp
        payload = await build_profile_payload_async(
            db,
            consultant,
            user,
            connected_providers=set(),
            primary_email="c1@example.com",
            primary_email_verified=True,
            has_usable_password=True,
            yandex_oauth_enabled=False,
            use_cache=False,
        )
        assert payload["profile"]["id"] == consultant.id

    await engine.dispose()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_page_context_async_no_user():
    from app.templating import page_context_async

    request = MagicMock()
    request.url.path = "/booking/"
    request.scope = {}
    ctx = await page_context_async(request, db=None, user=None, success="ok")
    assert ctx["cabinet_nav_active"] == "bookings"
    assert ctx["success"] == "ok"
    assert ctx["has_consultant"] is False
    assert "csrf_token" in ctx
