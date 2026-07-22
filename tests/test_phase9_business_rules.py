"""Phase 9: self-booking, ClientCard merge, reschedule notify, audit, metrics."""
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import (
    Booking,
    Calendar,
    Category,
    ClientCard,
    Consultant,
    Integration,
    IntegrationTelegramAudit,
    Service,
    TimeSlot,
    User,
)
from app.services.app_counters import DEDUP_HITS_KEY, get_counter, record_notify_dedup_hit
from app.services.bookings import find_or_create_client_card, reschedule_booking
from app.services.dual_role_inventory import collect_dual_role_inventory
from app.services.integration_telegram import claim_integration_telegram_chat, clear_integration_telegram_chat
from app.services.telegram import format_booking_rescheduled_client


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_calendar(db, *, user_id=None):
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="a@t.c",
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
        book_ahead_hours=0,
        max_services_per_day=0,
        break_between_services_minutes=0,
    )
    db.add(cal)
    db.flush()
    # Mon=0 .. use today weekday
    dow = date.today().weekday()
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
    return c, cal, svc


def test_self_booking_blocked():
    from app.services.bookings import create_public_booking

    db = _session()
    user = User(username="self", password="x", email="self@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    c, cal, svc = _seed_calendar(db, user_id=user.id)
    day = date.today() + timedelta(days=1)
    # ensure timeslot for that weekday
    dow = day.weekday()
    if not db.query(TimeSlot).filter(TimeSlot.calendar_id == cal.id, TimeSlot.day_of_week == dow).first():
        db.add(
            TimeSlot(
                calendar_id=cal.id,
                day_of_week=dow,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_available=True,
            )
        )
        db.commit()

    booking, err = create_public_booking(
        db,
        cal,
        svc.id,
        day,
        "10:00",
        "11:00",
        "Me",
        "79991112233",
        "",
        "",
        client_user_id=user.id,
    )
    assert booking is None
    assert err and "самому себе" in err
    db.close()


def test_client_card_no_blind_merge_across_users():
    db = _session()
    u1 = User(username="u1", password="x", email="u1@t.c", date_joined=datetime.now())
    u2 = User(username="u2", password="x", email="u2@t.c", date_joined=datetime.now())
    db.add_all([u1, u2])
    db.flush()
    c, _, _ = _seed_calendar(db)

    card1 = find_or_create_client_card(
        db, c, "One", "79990001111", "", "", client_user_id=u1.id
    )
    card2 = find_or_create_client_card(
        db, c, "Two", "79990001111", "", "", client_user_id=u2.id
    )
    assert card1.id != card2.id
    assert card1.client_user_id == u1.id
    assert card2.client_user_id == u2.id
    assert db.query(ClientCard).filter(ClientCard.consultant_id == c.id).count() == 2
    db.close()


def test_reschedule_sends_telegram_notify():
    db = _session()
    c, cal, svc = _seed_calendar(db)
    day = date.today() + timedelta(days=2)
    dow = day.weekday()
    if not db.query(TimeSlot).filter(TimeSlot.calendar_id == cal.id, TimeSlot.day_of_week == dow).first():
        db.add(
            TimeSlot(
                calendar_id=cal.id,
                day_of_week=dow,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_available=True,
            )
        )
        db.commit()
    b = Booking(
        service_id=svc.id,
        calendar_id=cal.id,
        client_name="X",
        client_phone="7999",
        booking_date=day,
        booking_time=time(10, 0),
        booking_end_time=time(11, 0),
        status="confirmed",
        telegram_id=111,
    )
    db.add(b)
    db.commit()

    new_day = day + timedelta(days=1)
    ndow = new_day.weekday()
    if not db.query(TimeSlot).filter(TimeSlot.calendar_id == cal.id, TimeSlot.day_of_week == ndow).first():
        db.add(
            TimeSlot(
                calendar_id=cal.id,
                day_of_week=ndow,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_available=True,
            )
        )
        db.commit()

    with patch("app.services.bookings.notify_booking_rescheduled") as mock_n:
        with patch("app.services.bookings.on_booking_updated"):
            err = reschedule_booking(db, b, new_day, "12:00")
    assert err is None
    assert mock_n.called
    kwargs = mock_n.call_args.kwargs
    assert kwargs.get("old_date") == day
    assert kwargs.get("old_time") == time(10, 0)
    text = format_booking_rescheduled_client(b, old_date=day, old_time=time(10, 0))
    assert "перенесена" in text
    db.close()


def test_integration_chat_audit():
    db = _session()
    c, _, _ = _seed_calendar(db)
    integ = Integration(consultant_id=c.id)
    db.add(integ)
    db.commit()

    ok, _ = claim_integration_telegram_chat(db, integ, "555001", source="test")
    assert ok
    db.commit()
    rows = db.query(IntegrationTelegramAudit).all()
    assert len(rows) == 1
    assert rows[0].new_chat_id == "555001"
    assert rows[0].old_chat_id is None

    clear_integration_telegram_chat(db, integ, source="test_clear")
    db.commit()
    rows2 = db.query(IntegrationTelegramAudit).order_by(IntegrationTelegramAudit.id).all()
    assert len(rows2) == 2
    assert rows2[-1].new_chat_id is None
    assert rows2[-1].old_chat_id == "555001"
    db.close()


def test_inventory_dual_and_dedup_counter():
    db = _session()
    user = User(username="dual", password="x", email="d@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    _seed_calendar(db, user_id=user.id)
    from app.models import SocialAccount

    db.add(SocialAccount(provider="telegram", uid="999", user_id=user.id, extra_data="{}"))
    db.commit()
    record_notify_dedup_hit(db)
    db.commit()

    data = collect_dual_role_inventory(db)
    assert data["dual_users_count"] >= 1
    assert data["notify_dedup_hits"] == get_counter(db, DEDUP_HITS_KEY) == 1
    assert data["orphan_users_count"] >= 0
    db.close()
