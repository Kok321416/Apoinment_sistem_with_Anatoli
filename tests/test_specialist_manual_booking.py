"""Tests for specialist-created bookings."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bookings import (
    create_specialist_booking_async,
    normalize_client_phone,
    normalize_optional_email,
)


def test_normalize_phone_empty_ok():
    assert normalize_client_phone("") == ("", None)
    assert normalize_client_phone("   ") == ("", None)


def test_normalize_phone_required():
    phone, err = normalize_client_phone("", required=True)
    assert phone == ""
    assert err


def test_normalize_phone_invalid():
    phone, err = normalize_client_phone("123")
    assert phone == ""
    assert err


def test_normalize_phone_ru_mobile():
    phone, err = normalize_client_phone("+7 (999) 123-45-67")
    assert err is None
    assert phone == "+79991234567"
    phone2, err2 = normalize_client_phone("89991234567")
    assert err2 is None
    assert phone2 == "+79991234567"


def test_normalize_email_optional():
    assert normalize_optional_email("") == (None, None)
    assert normalize_optional_email("bad")[1]
    val, err = normalize_optional_email("a@b.co")
    assert err is None
    assert val == "a@b.co"


@pytest.mark.asyncio
async def test_search_client_cards_by_name_and_telegram():
    from app.services.bookings import search_client_cards_async

    card_a = MagicMock(id=1, name="Вася Пупкин", telegram="@vasya", phone=None, email=None)
    card_b = MagicMock(id=2, name="Мария", telegram="@mary", phone=None, email=None)

    async def execute(stmt):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [card_a]
        return result

    db = AsyncMock()
    db.execute = execute
    rows = await search_client_cards_async(db, consultant_id=1, query="вас")
    assert rows == [card_a]

    rows_empty = await search_client_cards_async(db, consultant_id=1, query="  ")
    assert rows_empty == []



@pytest.mark.asyncio
async def test_specialist_booking_requires_name():
    db = AsyncMock()
    consultant = MagicMock(id=1)
    booking, err, matches = await create_specialist_booking_async(
        db,
        consultant,
        calendar_id=1,
        service_id=1,
        booking_date=date.today() + timedelta(days=1),
        booking_time_str="10:00",
        booking_end_time_str="11:00",
        client_name="   ",
    )
    assert booking is None
    assert err == "Укажите ФИО клиента"
    assert matches is None


@pytest.mark.asyncio
async def test_specialist_booking_missing_calendar():
    db = AsyncMock()
    consultant = MagicMock(id=1)

    async def execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = execute
    booking, err, _ = await create_specialist_booking_async(
        db,
        consultant,
        calendar_id=99,
        service_id=1,
        booking_date=date.today() + timedelta(days=1),
        booking_time_str="10:00",
        booking_end_time_str="11:00",
        client_name="Иванов Иван",
    )
    assert booking is None
    assert "Календарь" in (err or "")


@pytest.mark.asyncio
async def test_specialist_booking_slot_taken():
    db = AsyncMock()
    consultant = MagicMock(id=1)
    calendar = MagicMock(
        id=1,
        consultant_id=1,
        is_active=True,
        max_services_per_day=0,
        break_between_services_minutes=0,
        book_ahead_hours=0,
    )
    service = MagicMock(
        id=2,
        consultant_id=1,
        is_active=True,
        calendar_id=1,
        duration_minutes=60,
    )
    time_slot = MagicMock(
        id=3,
        calendar_id=1,
        day_of_week=(date.today() + timedelta(days=1)).weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
        is_available=True,
    )
    taken = MagicMock(id=10)

    calls = {"n": 0}

    async def execute(stmt):
        calls["n"] += 1
        result = MagicMock()
        # calendar, service, lock calendar, time_slot, slot_taken
        n = calls["n"]
        if n == 1:
            result.scalar_one_or_none.return_value = calendar
            result.scalar_one.return_value = calendar
        elif n == 2:
            result.scalar_one_or_none.return_value = service
        elif n == 3:
            result.scalar_one.return_value = calendar
        elif n == 4:
            result.scalar_one_or_none.return_value = time_slot
        elif n == 5:
            result.scalar_one_or_none.return_value = taken
        else:
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        return result

    db.execute = execute
    booking, err, _ = await create_specialist_booking_async(
        db,
        consultant,
        calendar_id=1,
        service_id=2,
        booking_date=date.today() + timedelta(days=1),
        booking_time_str="10:00",
        booking_end_time_str="11:00",
        client_name="Иванов Иван",
        force_new_client=True,
    )
    assert booking is None
    assert "занято" in (err or "").lower()
