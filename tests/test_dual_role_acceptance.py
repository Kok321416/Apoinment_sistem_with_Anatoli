"""Dual-role E2E acceptance tests (checklist section D + guest booking)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, Integration, Service, TimeSlot, User
from app.services.bookings import create_public_booking
from app.services.integration_telegram import claim_integration_telegram_chat


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db, *, user_id=None, consultant_email="a@t.c"):
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email=consultant_email,
        phone="+79991112233",
        category_of_specialist_id=cat.id,
        user_id=user_id,
    )
    db.add(c)
    db.flush()
    cal = Calendar(
        consultant_id=c.id,
        name="Cal",
        color="#7d5cff",
        book_ahead_hours=1,
        max_services_per_day=0,
        break_between_services_minutes=0,
    )
    db.add(cal)
    db.flush()
    day = date.today() + timedelta(days=3)
    dow = day.weekday()
    db.add(
        TimeSlot(
            calendar_id=cal.id,
            day_of_week=dow,
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_available=True,
        )
    )
    svc = Service(
        consultant_id=c.id,
        calendar_id=cal.id,
        name="Consult",
        duration_minutes=60,
        is_active=True,
    )
    db.add(svc)
    db.commit()
    return c, cal, svc, day


def test_guest_booking_without_user_still_works():
    db = _session()
    _c, cal, svc, day = _seed(db)
    booking, err = create_public_booking(
        db,
        cal,
        svc.id,
        day,
        "10:00",
        "11:00",
        "Guest",
        "79990001111",
        "",
        "",
        client_user_id=None,
    )
    assert err is None
    assert booking is not None
    assert booking.client_user_id is None
    db.close()


def test_integration_chat_id_conflict_rejected():
    db = _session()
    c1, _, _, _ = _seed(db, consultant_email="one@t.c")
    c2, _, _, _ = _seed(db, consultant_email="two@t.c")
    integ1 = Integration(consultant_id=c1.id)
    integ2 = Integration(consultant_id=c2.id)
    db.add_all([integ1, integ2])
    db.commit()

    ok1, _ = claim_integration_telegram_chat(db, integ1, "777001", source="test")
    assert ok1
    db.commit()
    ok2, msg2 = claim_integration_telegram_chat(db, integ2, "777001", source="test")
    assert not ok2
    assert "другому специалисту" in msg2
    db.close()


def test_active_mode_session_helpers():
    from app.services.active_mode import set_active_mode
    from starlette.requests import Request

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
    set_active_mode(request, "client", has_consultant=True)
    assert request.session.get("active_mode") == "client"
    set_active_mode(request, "specialist", has_consultant=True)
    assert request.session.get("active_mode") == "specialist"
