"""Phase 6 active_mode and client bookings list."""
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, SocialAccount, User
from app.services.active_mode import list_client_bookings


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_list_client_bookings_by_user_and_telegram_fallback():
    db = _session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    user = User(username="u", password="x", email="u@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="c@t.c",
        phone="+7999",
        category_of_specialist_id=cat.id,
        user_id=None,
    )
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()
    db.add(SocialAccount(provider="telegram", uid="888001", user_id=user.id, extra_data="{}"))

    b1 = Booking(
        service_id=1,
        calendar_id=cal.id,
        client_name="Me",
        client_phone="+1",
        booking_date=date.today(),
        booking_time=time(10, 0),
        status="pending",
        client_user_id=user.id,
    )
    b2 = Booking(
        service_id=1,
        calendar_id=cal.id,
        client_name="Me2",
        client_phone="+2",
        booking_date=date.today(),
        booking_time=time(11, 0),
        status="confirmed",
        telegram_id=888001,
        client_user_id=None,
    )
    db.add_all([b1, b2])
    db.commit()

    rows = list_client_bookings(db, user.id)
    ids = {b.id for b in rows}
    assert b1.id in ids
    assert b2.id in ids
    db.close()
