"""Tests for dual-role Phase 2 backfill."""
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, SocialAccount, User
from app.services.dual_role_backfill import (
    backfill_booking_client_user_ids,
    resolve_client_user_id_for_telegram,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_backfill_links_unique_social_and_skips_ambiguous():
    db = _session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()

    u1 = User(username="u1", password="x", email="u1@t.c", date_joined=datetime.now())
    u2 = User(username="u2", password="x", email="u2@t.c", date_joined=datetime.now())
    u3 = User(username="u3", password="x", email="u3@t.c", date_joined=datetime.now())
    db.add_all([u1, u2, u3])
    db.flush()

    c = Consultant(
        first_name="A",
        last_name="B",
        email="c@t.c",
        phone="+7999",
        category_of_specialist_id=cat.id,
        user_id=u1.id,
    )
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()

    db.add(SocialAccount(provider="telegram", uid="111", user_id=u1.id, extra_data="{}"))
    db.add(SocialAccount(provider="telegram", uid="222", user_id=u2.id, extra_data="{}"))
    db.add(SocialAccount(provider="telegram", uid="222", user_id=u3.id, extra_data="{}"))

    b_ok = Booking(
        service_id=1,
        calendar_id=cal.id,
        client_name="Ok",
        client_phone="+1",
        booking_date=date.today(),
        booking_time=time(10, 0),
        status="pending",
        telegram_id=111,
    )
    b_ambiguous = Booking(
        service_id=1,
        calendar_id=cal.id,
        client_name="Amb",
        client_phone="+2",
        booking_date=date.today(),
        booking_time=time(11, 0),
        status="pending",
        telegram_id=222,
    )
    b_none = Booking(
        service_id=1,
        calendar_id=cal.id,
        client_name="None",
        client_phone="+3",
        booking_date=date.today(),
        booking_time=time(12, 0),
        status="pending",
        telegram_id=333,
    )
    db.add_all([b_ok, b_ambiguous, b_none])
    db.commit()

    dry = backfill_booking_client_user_ids(db, dry_run=True)
    assert dry["updated"] == 1
    assert dry["skipped_ambiguous"] == 1
    assert dry["skipped_no_user"] == 1
    db.refresh(b_ok)
    assert b_ok.client_user_id is None

    applied = backfill_booking_client_user_ids(db, dry_run=False)
    assert applied["updated"] == 1
    db.refresh(b_ok)
    db.refresh(b_ambiguous)
    db.refresh(b_none)
    assert b_ok.client_user_id == u1.id
    assert b_ambiguous.client_user_id is None
    assert b_none.client_user_id is None

    # Idempotent second run
    again = backfill_booking_client_user_ids(db, dry_run=False)
    assert again["candidates"] == 2  # ambiguous + none still open
    assert again["updated"] == 0
    db.close()


def test_resolve_client_user_id_for_telegram():
    db = _session()
    u = User(username="r", password="x", email="r@t.c", date_joined=datetime.now())
    db.add(u)
    db.flush()
    db.add(SocialAccount(provider="telegram", uid="555", user_id=u.id, extra_data="{}"))
    db.commit()
    assert resolve_client_user_id_for_telegram(db, 555) == u.id
    assert resolve_client_user_id_for_telegram(db, "555") == u.id
    assert resolve_client_user_id_for_telegram(db, 999) is None
    db.close()
