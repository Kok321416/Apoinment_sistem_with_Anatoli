"""P0/P1: Telegram client booking notifications and duplicate protection."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_async_db
from app.main import app
from app.models import (
    Booking,
    Calendar,
    Category,
    Consultant,
    Integration,
    Service,
    SocialAccount,
    TimeSlot,
    User,
)
from app.services.bookings import create_public_booking
from app.services.dual_role_backfill import (
    resolve_telegram_id_for_user,
    resolve_telegram_id_for_user_async,
)
from app.services import telegram as tg


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db, *, book_ahead_hours=0):
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    consultant = Consultant(
        first_name="Spec",
        last_name="A",
        email="spec@t.c",
        phone="+79991112233",
        category_of_specialist_id=cat.id,
    )
    db.add(consultant)
    db.flush()
    calendar = Calendar(
        consultant_id=consultant.id,
        name="Cal",
        color="#7d5cff",
        book_ahead_hours=book_ahead_hours,
        max_services_per_day=0,
        break_between_services_minutes=0,
    )
    db.add(calendar)
    db.flush()
    day = date.today() + timedelta(days=3)
    db.add(
        TimeSlot(
            calendar_id=calendar.id,
            day_of_week=day.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_available=True,
        )
    )
    service = Service(
        consultant_id=consultant.id,
        calendar_id=calendar.id,
        name="Consult",
        duration_minutes=60,
        is_active=True,
    )
    db.add(service)
    db.commit()
    return consultant, calendar, service, day


def _telegram_user(db, *, uid: str = "424242") -> User:
    user = User(
        username=f"tg_{uid}",
        password="x",
        email=f"{uid}@telegram.user",
        date_joined=datetime.now(),
    )
    db.add(user)
    db.flush()
    db.add(SocialAccount(provider="telegram", uid=uid, user_id=user.id))
    db.commit()
    return user


def _capture_notifications():
    sent = []

    def capture_sync(chat_id, text, bot_token=None, **kwargs):
        sent.append((chat_id, kwargs.get("recipient_type"), text))
        return True

    def capture_async(chat_id, text, bot_token=None, **kwargs):
        sent.append((chat_id, kwargs.get("recipient_type"), text))
        return None

    return sent, capture_sync, capture_async


def _booking_kwargs(cal, svc, day):
    return dict(
        calendar=cal,
        service_id=svc.id,
        booking_date=day,
        booking_time_str="10:00",
        booking_end_time_str="11:00",
        client_name="Client",
        client_phone="79990001111",
        client_email="",
        client_telegram="",
    )


def test_resolve_telegram_id_for_user_from_social_account():
    db = _session()
    user = _telegram_user(db, uid="555001")
    assert resolve_telegram_id_for_user(db, user.id) == 555001
    assert resolve_telegram_id_for_user(db, None) is None
    db.close()


def test_resolve_telegram_id_invalid_uid_returns_none():
    db = _session()
    user = User(username="bad", password="x", email="b@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    db.add(SocialAccount(provider="telegram", uid="not-a-number", user_id=user.id))
    db.commit()
    assert resolve_telegram_id_for_user(db, user.id) is None
    db.close()


@pytest.mark.asyncio
async def test_resolve_telegram_id_for_user_async():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        user = User(username="tg_a", password="x", email="a@t.c", date_joined=datetime.now())
        db.add(user)
        await db.flush()
        db.add(SocialAccount(provider="telegram", uid="888777", user_id=user.id))
        await db.commit()
        assert await resolve_telegram_id_for_user_async(db, user.id) == 888777
    await engine.dispose()


def test_telegram_client_booking_populates_telegram_id_and_notifies_client():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    user = _telegram_user(db, uid="100200")
    sent, capture_sync, capture_async = _capture_notifications()

    with (
        patch.object(tg, "_send_telegram", side_effect=capture_sync),
        patch.object(tg, "send_telegram_async", side_effect=capture_async),
        patch.object(tg, "notify_specialist_new_booking", return_value=False),
    ):
        booking, err = create_public_booking(
            db, client_user_id=user.id, **_booking_kwargs(cal, svc, day)
        )
    assert err is None
    assert booking.telegram_id == 100200
    assert len(sent) == 1
    assert int(sent[0][0]) == 100200
    assert sent[0][1] == "client"
    assert "Вы записались" in sent[0][2]
    db.close()


def test_both_telegram_client_and_specialist_get_separate_notifications():
    db = _session()
    consultant, cal, svc, day = _seed(db)
    user = _telegram_user(db, uid="300400")
    integration = Integration(
        consultant_id=consultant.id,
        telegram_connected=True,
        telegram_enabled=True,
        telegram_chat_id="900001",
    )
    db.add(integration)
    db.commit()

    sent, capture_sync, capture_async = _capture_notifications()

    with (
        patch.object(tg, "_send_telegram", side_effect=capture_sync),
        patch.object(tg, "send_telegram_async", side_effect=capture_async),
    ):
        booking, err = create_public_booking(
            db, client_user_id=user.id, **_booking_kwargs(cal, svc, day)
        )
    assert err is None
    recipients = {str(item[0]) for item in sent}
    types = {item[1] for item in sent}
    assert "300400" in recipients
    assert "900001" in recipients
    assert "client" in types
    assert "specialist" in types
    assert booking.telegram_id == 300400
    db.close()


def test_email_user_skips_telegram_client_notification():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    user = User(username="mail", password="x", email="client@example.com", date_joined=datetime.now())
    db.add(user)
    db.commit()

    with patch.object(tg, "send_telegram_async") as mock_tg, patch(
        "app.services.booking_email.notify_client_via_email_if_no_telegram", return_value=True
    ) as mock_mail, patch.object(tg, "notify_specialist_new_booking", return_value=False):
        kwargs = _booking_kwargs(cal, svc, day)
        kwargs["client_email"] = "client@example.com"
        booking, err = create_public_booking(
            db,
            client_user_id=user.id,
            **kwargs,
        )
    assert err is None
    assert booking.telegram_id is None
    mock_tg.assert_not_called()
    mock_mail.assert_called_once()
    db.close()


def test_anonymous_booking_succeeds_without_telegram():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    with patch("app.services.bookings.on_booking_created") as mock_notify:
        booking, err = create_public_booking(
            db, client_user_id=None, **_booking_kwargs(cal, svc, day)
        )
    assert err is None
    assert booking.telegram_id is None
    mock_notify.assert_called_once()
    db.close()


def test_specialist_without_integration_client_still_notified():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    user = _telegram_user(db, uid="501502")
    sent, capture_sync, capture_async = _capture_notifications()

    with (
        patch.object(tg, "_send_telegram", side_effect=capture_sync),
        patch.object(tg, "send_telegram_async", side_effect=capture_async),
    ):
        booking, err = create_public_booking(
            db, client_user_id=user.id, **_booking_kwargs(cal, svc, day)
        )
    assert err is None
    assert booking.telegram_id == 501502
    assert len(sent) == 1
    assert sent[0][1] == "client"
    db.close()


def test_telegram_send_failure_does_not_rollback_booking():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    user = _telegram_user(db, uid="601602")

    with patch.object(tg, "_send_telegram", return_value=False), patch.object(
        tg, "notify_specialist_new_booking", return_value=False
    ):
        booking, err = create_public_booking(
            db, client_user_id=user.id, **_booking_kwargs(cal, svc, day)
        )
    assert err is None
    persisted = db.query(Booking).filter(Booking.id == booking.id).one()
    assert persisted.telegram_id == 601602
    db.close()


def _async_test_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare_schema())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db
    return engine, session_factory, TestClient(app)


def _close_async_test_client(engine):
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _seed_async_booking(session_factory, *, link_token: str, telegram_id: int | None = None):
    async with session_factory() as db:
        cat = Category(name_category="Общая")
        db.add(cat)
        await db.flush()
        consultant = Consultant(
            first_name="Spec",
            last_name="A",
            email="spec@t.c",
            phone="+7999",
            category_of_specialist_id=cat.id,
        )
        db.add(consultant)
        await db.flush()
        cal = Calendar(
            consultant_id=consultant.id,
            name="Cal",
            color="#000",
            book_ahead_hours=0,
            max_services_per_day=0,
            break_between_services_minutes=0,
        )
        db.add(cal)
        await db.flush()
        day = date.today() + timedelta(days=3)
        svc = Service(
            consultant_id=consultant.id,
            calendar_id=cal.id,
            name="S",
            duration_minutes=60,
            is_active=True,
        )
        db.add(svc)
        await db.flush()
        booking = Booking(
            service_id=svc.id,
            calendar_id=cal.id,
            booking_date=day,
            booking_time=time(10, 0),
            booking_end_time=time(11, 0),
            client_name="Client",
            client_phone="+7999",
            status="pending",
            link_token=link_token,
            telegram_id=telegram_id,
        )
        db.add(booking)
        await db.commit()
        return booking.id


def test_confirm_telegram_first_link_sends_once():
    engine, session_factory, client = _async_test_client()
    try:
        asyncio.run(_seed_async_booking(session_factory, link_token="tok123", telegram_id=None))
        sent = []
        with patch("app.routers.api.verify_bot_request", return_value=True), patch(
            "app.routers.api.send_telegram_to_client",
            side_effect=lambda tid, text, **kw: sent.append(tid) or True,
        ):
            r = client.post(
                "/api/booking/confirm-telegram",
                content=json.dumps({"link_token": "tok123", "telegram_id": 777888}),
                headers={"Content-Type": "application/json"},
            )
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert sent == [777888]

        async def _check():
            async with session_factory() as db:
                row = (
                    await db.execute(select(Booking.telegram_id).where(Booking.link_token.is_(None)))
                ).scalar_one()
                assert row == 777888

        asyncio.run(_check())
    finally:
        _close_async_test_client(engine)


def test_confirm_telegram_after_p0_does_not_duplicate():
    engine, session_factory, client = _async_test_client()
    try:
        asyncio.run(_seed_async_booking(session_factory, link_token="tok456", telegram_id=424242))
        with patch("app.routers.api.verify_bot_request", return_value=True), patch(
            "app.routers.api.send_telegram_to_client"
        ) as mock_send:
            r = client.post(
                "/api/booking/confirm-telegram",
                content=json.dumps({"link_token": "tok456", "telegram_id": 424242}),
                headers={"Content-Type": "application/json"},
            )
        assert r.status_code == 200
        mock_send.assert_not_called()
    finally:
        _close_async_test_client(engine)


def test_reminders_use_booking_telegram_id():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    cal.reminder_hours_first = 1
    cal.reminder_hours_second = 1
    booking = Booking(
        service_id=svc.id,
        calendar_id=cal.id,
        booking_date=day,
        booking_time=time(12, 0),
        booking_end_time=time(13, 0),
        client_name="Client",
        client_phone="+7999",
        status="confirmed",
        telegram_id=909090,
        reminder_24h_sent=False,
    )
    db.add(booking)
    db.commit()

    sent_to = []
    with patch.object(tg, "send_telegram_to_client", side_effect=lambda tid, text: sent_to.append(tid) or True):
        with patch.object(tg, "notify_dedup_enabled", return_value=False):
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("Europe/Moscow")
            now = datetime.combine(day, time(11, 30), tzinfo=tz)
            with patch("app.services.telegram.datetime") as mock_dt:
                mock_dt.now.return_value = now
                mock_dt.combine = datetime.combine
                tg.send_reminders(db)
    assert 909090 in sent_to
    db.close()


@pytest.mark.asyncio
async def test_create_public_booking_async_resolves_telegram_id():
    from app.services.bookings import create_public_booking_async

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        cat = Category(name_category="Общая")
        db.add(cat)
        await db.flush()
        consultant = Consultant(
            first_name="A",
            last_name="B",
            email="a@t.c",
            phone="+7999",
            category_of_specialist_id=cat.id,
        )
        db.add(consultant)
        await db.flush()
        cal = Calendar(
            consultant_id=consultant.id,
            name="Cal",
            color="#000",
            book_ahead_hours=0,
            max_services_per_day=0,
            break_between_services_minutes=0,
        )
        db.add(cal)
        await db.flush()
        day = date.today() + timedelta(days=3)
        db.add(
            TimeSlot(
                calendar_id=cal.id,
                day_of_week=day.weekday(),
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_available=True,
            )
        )
        svc = Service(
            consultant_id=consultant.id,
            calendar_id=cal.id,
            name="S",
            duration_minutes=60,
            is_active=True,
        )
        db.add(svc)
        await db.flush()
        user = User(username="u1", password="x", email="u@t.c", date_joined=datetime.now())
        db.add(user)
        await db.flush()
        db.add(SocialAccount(provider="telegram", uid="112233", user_id=user.id))
        await db.commit()

        with patch("app.services.notify_bridge.schedule_on_booking_created"):
            booking, err = await create_public_booking_async(
                db,
                cal,
                svc.id,
                day,
                "10:00",
                "11:00",
                "Client",
                "79990001111",
                "",
                "",
                client_user_id=user.id,
                consultant=consultant,
            )
        assert err is None
        assert booking.telegram_id == 112233
        row = (
            await db.execute(select(Booking.telegram_id).where(Booking.id == booking.id))
        ).scalar_one()
        assert row == 112233
    await engine.dispose()


def test_telegram_id_not_taken_from_client_telegram_field():
    db = _session()
    _consultant, cal, svc, day = _seed(db)
    kwargs = _booking_kwargs(cal, svc, day)
    kwargs["client_telegram"] = "@someuser"
    booking, err = create_public_booking(
        db,
        client_user_id=None,
        **kwargs,
    )
    assert err is None
    assert booking.telegram_id is None
    assert booking.client_telegram == "@someuser"
    db.close()
