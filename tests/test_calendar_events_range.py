"""/api/booking/calendar-events/ must cover the days the UI renders, not just one month.

The bookings page defaults to a week view and pads the month grid with adjacent days, but it used to
fetch whole months: a booking on 01.10 was missing from the week of 28.09 even though the specialist
had been notified about it. The endpoint now takes the rendered range.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.passwords import hash_password
from app.database import (
    Base,
    configure_async_sessionmaker,
    get_async_db,
    reset_async_sessionmaker,
)
from app.models import Booking, Calendar, Category, Consultant, Service, User

SPEC_EMAIL = "range-spec@test.com"
SPEC_PASSWORD = "rangepass"
BOOKINGS = [
    (date(2026, 8, 31), time(9, 0), "Август Крайний"),
    (date(2026, 9, 30), time(14, 30), "Сентябрь Последний"),
    (date(2026, 10, 1), time(13, 0), "Лозко Наталья Ивановна"),
    (date(2026, 10, 2), time(14, 15), "Октябрь Второй"),
]


@pytest.fixture()
def spec_client():
    from app.main import app

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            cat = Category(name_category="Общая")
            db.add(cat)
            await db.flush()
            user = User(
                username=SPEC_EMAIL,
                email=SPEC_EMAIL,
                password=hash_password(SPEC_PASSWORD),
                is_active=True,
                date_joined=datetime(2026, 1, 1),
            )
            db.add(user)
            await db.flush()
            consultant = Consultant(
                first_name="Диапазон",
                last_name="Тест",
                email=SPEC_EMAIL,
                phone="+79990001144",
                category_of_specialist_id=cat.id,
                user_id=user.id,
            )
            db.add(consultant)
            await db.flush()
            calendar = Calendar(consultant_id=consultant.id, name="325 кабинет запись", color="#000")
            db.add(calendar)
            await db.flush()
            service = Service(
                consultant_id=consultant.id,
                calendar_id=calendar.id,
                name="Консультация 325 кабинет",
                duration_minutes=60,
                is_active=True,
            )
            db.add(service)
            await db.flush()
            for booking_date, booking_time, client_name in BOOKINGS:
                db.add(
                    Booking(
                        service_id=service.id,
                        calendar_id=calendar.id,
                        booking_date=booking_date,
                        booking_time=booking_time,
                        client_name=client_name,
                        client_phone="+79021787730",
                        status="confirmed",
                    )
                )
            await db.commit()

    asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db
    configure_async_sessionmaker(session_factory, async_engine=engine)

    client = TestClient(app)
    page = client.get("/login/")
    csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
    assert csrf, "login page has no csrf token"
    client.post(
        "/login/",
        data={"login": SPEC_EMAIL, "password": SPEC_PASSWORD, "csrf_token": csrf.group(1)},
        follow_redirects=True,
    )
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        reset_async_sessionmaker()
        asyncio.run(engine.dispose())


def _dates(client: TestClient, **params) -> list[str]:
    r = client.get("/api/booking/calendar-events/", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    return [e["date"] for e in body["events"] if e.get("kind") == "booking"]


def test_week_crossing_month_boundary_returns_both_months(spec_client):
    """Week of Mon 28.09 — Sun 04.10: the October days must come back too."""
    dates = _dates(spec_client, start="2026-09-28", end="2026-10-04")

    assert dates == ["2026-09-30", "2026-10-01", "2026-10-02"]


def test_month_grid_padding_days_are_included(spec_client):
    """September grid renders 31.08 and 01–04.10 as adjacent-month cells."""
    dates = _dates(spec_client, start="2026-08-31", end="2026-10-04")

    assert "2026-08-31" in dates
    assert "2026-10-01" in dates


def test_single_day_range(spec_client):
    assert _dates(spec_client, start="2026-10-01", end="2026-10-01") == ["2026-10-01"]


def test_month_params_still_work_for_cached_clients(spec_client):
    assert _dates(spec_client, year=2026, month=9) == ["2026-09-30"]


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-10-04", "end": "2026-10-01"},
        {"start": "2026-01-01", "end": "2026-12-31"},
        {"start": "not-a-date", "end": "2026-10-04"},
        {"start": "2026-09-28"},
    ],
)
def test_invalid_ranges_are_rejected(spec_client, params):
    r = spec_client.get("/api/booking/calendar-events/", params=params)

    assert r.status_code == 200
    assert r.json() == {"success": False, "events": []}


def test_bookings_page_asks_for_the_rendered_range():
    """A month-wide request is what hid the bookings; keep the client asking per rendered range."""
    js = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "specialist-bookings.js"
    source = js.read_text(encoding="utf-8")

    assert "calendar-events/?start=" in source
    assert "calendar-events/?year=" not in source
    assert "renderedRange()" in source
