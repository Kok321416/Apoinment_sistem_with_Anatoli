"""Tests for calendar blocks (мероприятия)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.calendar_blocks import intervals_overlap, serialize_block
from app.services.slots import _compute_available_slots


def test_intervals_overlap_with_break():
    day = date(2026, 9, 10)
    a0 = datetime.combine(day, time(10, 0))
    a1 = datetime.combine(day, time(11, 0))
    b0 = datetime.combine(day, time(11, 0))
    b1 = datetime.combine(day, time(12, 0))
    assert intervals_overlap(a0, a1, b0, b1, break_delta=timedelta(minutes=0)) is False
    assert intervals_overlap(a0, a1, b0, b1, break_delta=timedelta(minutes=15)) is True


def test_serialize_block_kind_event():
    block = SimpleNamespace(
        id=7,
        title="Супервизия",
        notes="note",
        block_date=date(2026, 9, 12),
        start_time=time(14, 0),
        end_time=time(16, 0),
        status="active",
        calendar_id=3,
    )
    data = serialize_block(block)
    assert data["kind"] == "event"
    assert data["client_name"] == "Супервизия"
    assert data["time"] == "14:00"
    assert data["end_time"] == "16:00"
    assert data["service"] == "Мероприятие"


def test_slots_hide_times_covered_by_block():
    calendar = SimpleNamespace(
        max_services_per_day=0,
        break_between_services_minutes=0,
        book_ahead_hours=0,
        disabled_weekdays="",
        timezone=None,
    )
    service = SimpleNamespace(duration_minutes=60)
    booking_date = date(2099, 1, 5)  # Monday far future
    time_slots = [SimpleNamespace(start_time=time(10, 0), end_time=time(14, 0))]
    block = SimpleNamespace(start_time=time(11, 0), end_time=time(12, 0))

    result = _compute_available_slots(
        calendar=calendar,
        service=service,
        booking_date=booking_date,
        time_slots=time_slots,
        existing_bookings=[],
        busy_blocks=[block],
    )
    starts = {s["start_time"] for s in result["available_slots"]}
    assert "10:00" in starts
    assert "11:00" not in starts
    assert "12:00" in starts


@pytest.mark.asyncio
async def test_create_block_requires_title():
    from app.services.calendar_blocks import create_calendar_block_async

    db = AsyncMock()
    consultant = MagicMock(id=1)
    block, err = await create_calendar_block_async(
        db,
        consultant,
        calendar_id=1,
        title="  ",
        block_date=date(2026, 9, 12),
        start_time_str="10:00",
        end_time_str="11:00",
    )
    assert block is None
    assert err


@pytest.mark.asyncio
async def test_create_block_end_before_start():
    from app.services.calendar_blocks import create_calendar_block_async

    calendar = MagicMock(id=1, is_active=True, break_between_services_minutes=0)

    async def execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = calendar
        result.scalar_one.return_value = calendar
        result.scalars.return_value.all.return_value = []
        return result

    db = AsyncMock()
    db.execute = execute
    consultant = MagicMock(id=1)
    block, err = await create_calendar_block_async(
        db,
        consultant,
        calendar_id=1,
        title="Митинг",
        block_date=date(2026, 9, 12),
        start_time_str="12:00",
        end_time_str="11:00",
    )
    assert block is None
    assert "позже" in (err or "")
