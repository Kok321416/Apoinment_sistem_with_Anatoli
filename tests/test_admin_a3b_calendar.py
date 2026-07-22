"""Admin A3b: week calendar view."""
from datetime import date, time, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, Service, User
from app.services.platform_admin_calendar import (
    bookings_for_week,
    build_week_calendar,
    parse_week_start,
    week_range_label,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_booking(db, *, booking_date: date, booking_time: time, status="confirmed"):
    cat = Category(name_category="X")
    db.add(cat)
    db.flush()
    c = Consultant(first_name="A", last_name="B", email="a@t.c", phone="1", category_of_specialist_id=cat.id)
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Main", color="#7d5cff")
    db.add(cal)
    db.flush()
    svc = Service(consultant_id=c.id, calendar_id=cal.id, name="Svc", duration_minutes=60)
    db.add(svc)
    db.flush()
    b = Booking(
        service_id=svc.id,
        calendar_id=cal.id,
        client_name="Client",
        client_phone="1",
        booking_date=booking_date,
        booking_time=booking_time,
        status=status,
    )
    db.add(b)
    db.commit()
    return cal, b


def test_parse_week_start_monday():
    ws = parse_week_start("2026-07-22")  # Wednesday
    assert ws.weekday() == 0
    assert ws.isoformat() == "2026-07-20"


def test_week_calendar_groups_events():
    db = _session()
    ws = parse_week_start(None)
    cal, b = _seed_booking(db, booking_date=ws, booking_time=time(10, 30))
    rows = bookings_for_week(db, ws, calendar_id=cal.id)
    assert len(rows) == 1
    grid = build_week_calendar(rows, ws, today=ws)
    assert grid["total_events"] == 1
    assert grid["days"][0]["events"][0]["id"] == b.id
    assert grid["days"][0]["events"][0]["top_pct"] >= 0
    assert week_range_label(ws)
    db.close()


def test_week_navigation_dates():
    ws = date(2026, 7, 20)
    grid = build_week_calendar([], ws)
    assert grid["prev_week"] == "2026-07-13"
    assert grid["next_week"] == "2026-07-27"
