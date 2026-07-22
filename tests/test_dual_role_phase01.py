"""Tests for dual-role Phase 0 inventory and Phase 1 schema."""
from datetime import date, datetime, time

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, Integration, SocialAccount, User
from app.services.dual_role_inventory import collect_dual_role_inventory, format_inventory_report
from app.services.telegram import same_telegram_chat


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def test_same_telegram_chat_normalizes():
    assert same_telegram_chat(123, "123")
    assert same_telegram_chat(" 42 ", 42)
    assert not same_telegram_chat(1, 2)
    assert not same_telegram_chat(None, 1)


def test_schema_patch_adds_client_user_id():
    from app.db_schema import ensure_app_schema
    import app.db_schema as schema_mod

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE bookings ("
                "id INTEGER PRIMARY KEY, service_id INTEGER, calendar_id INTEGER, "
                "client_name VARCHAR(255), client_phone VARCHAR(20), "
                "booking_date DATE, booking_time TIME, status VARCHAR(20))"
            )
        )

    schema_mod.engine = engine
    schema_mod._SCHEMA_PATCHES_ATTEMPTED = False
    ensure_app_schema()

    cols = {c["name"] for c in inspect(engine).get_columns("bookings")}
    assert "client_user_id" in cols


def test_inventory_detects_orphan_shared_and_dual():
    db, _engine = _session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()

    orphan = User(username="orphan", password="x", email="o@t.c", date_joined=datetime.utcnow())
    specialist_user = User(username="spec", password="x", email="s@t.c", date_joined=datetime.utcnow())
    db.add_all([orphan, specialist_user])
    db.flush()

    c = Consultant(
        first_name="A",
        last_name="B",
        email="spec@t.c",
        phone="+7999",
        category_of_specialist_id=cat.id,
        user_id=specialist_user.id,
    )
    db.add(c)
    db.flush()

    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()

    integ = Integration(
        consultant_id=c.id,
        telegram_connected=True,
        telegram_enabled=True,
        telegram_chat_id="999001",
    )
    db.add(integ)

    # Second consultant sharing same chat (collision)
    c2 = Consultant(
        first_name="C",
        last_name="D",
        email="spec2@t.c",
        phone="+7888",
        category_of_specialist_id=cat.id,
        user_id=None,
    )
    db.add(c2)
    db.flush()
    db.add(
        Integration(
            consultant_id=c2.id,
            telegram_connected=True,
            telegram_enabled=True,
            telegram_chat_id="999001",
        )
    )

    db.add(SocialAccount(provider="telegram", uid="999001", user_id=specialist_user.id, extra_data="{}"))
    db.add(
        SocialAccount(provider="telegram", uid="999001", user_id=orphan.id, extra_data="{}")
    )  # duplicate uid

    booking = Booking(
        service_id=1,
        calendar_id=cal.id,
        client_name="Клиент",
        client_phone="+7000",
        booking_date=date.today(),
        booking_time=time(12, 0),
        status="pending",
        telegram_id=999001,
        client_user_id=None,
    )
    db.add(booking)
    db.commit()

    data = collect_dual_role_inventory(db)
    assert data["orphan_users_count"] >= 1
    assert data["shared_integration_chats_count"] >= 1
    assert data["dual_channel_bookings_count"] >= 1
    assert data["duplicate_telegram_social_uids_count"] >= 1
    assert data["bookings_tg_linkable_via_social"] >= 1
    assert data["schema_has_client_user_id"] is True
    report = format_inventory_report(data)
    assert "Dual-role inventory" in report
    db.close()
