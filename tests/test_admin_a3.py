"""Admin A3: specialists, clients, bookings, calendars, security."""
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import AdminAuditLog, Booking, Calendar, Category, ClientCard, Consultant, Service, User
from app.services.admin_audit import write_admin_audit
from app.services.platform_admin_domain import (
    admin_set_booking_status,
    list_bookings,
    list_calendars,
    list_failed_logins,
    platform_client_detail,
    search_platform_clients,
    search_specialists,
    set_calendar_active,
    specialist_admin_card,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_consultant(db):
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="Ann",
        last_name="Spec",
        email="spec@t.c",
        phone="+7999",
        category_of_specialist_id=cat.id,
    )
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Main", color="#7d5cff", is_active=True)
    db.add(cal)
    db.flush()
    svc = Service(
        consultant_id=c.id,
        calendar_id=cal.id,
        name="Услуга",
        duration_minutes=60,
        price=100,
    )
    db.add(svc)
    db.flush()
    card = ClientCard(consultant_id=c.id, name="Client One", phone="+7111", email="c@t.c")
    db.add(card)
    db.flush()
    u = User(username="client@t.c", password="x", email="client@t.c", date_joined=datetime.now())
    db.add(u)
    db.flush()
    card.client_user_id = u.id
    b1 = Booking(
        service_id=svc.id,
        calendar_id=cal.id,
        client_card_id=card.id,
        client_user_id=u.id,
        client_name="Client One",
        client_phone="+7111",
        booking_date=date.today(),
        booking_time=time(10, 0),
        status="pending",
    )
    b2 = Booking(
        service_id=svc.id,
        calendar_id=cal.id,
        client_card_id=card.id,
        client_user_id=u.id,
        client_name="Client One",
        client_phone="+7111",
        booking_date=date.today(),
        booking_time=time(12, 0),
        status="cancelled",
    )
    db.add_all([b1, b2])
    db.commit()
    return c, cal, u, card, b1


def test_specialist_stats_and_search():
    db = _session()
    c, _cal, _u, _card, _b1 = _seed_consultant(db)
    rows = search_specialists(db, "Ann")
    assert len(rows) == 1
    assert rows[0]["stats"]["bookings_total"] == 2
    assert rows[0]["stats"]["bookings_cancelled"] == 1
    assert rows[0]["stats"]["cancel_rate_pct"] == 50.0
    card = specialist_admin_card(db, c.id)
    assert card and card["consultant"].id == c.id
    db.close()


def test_platform_clients_search_and_detail():
    db = _session()
    _c, _cal, u, card, _b1 = _seed_consultant(db)
    rows = search_platform_clients(db, "client@")
    assert any(r.get("client_user_id") == u.id for r in rows)
    detail = platform_client_detail(db, user_id=u.id)
    assert detail and len(detail["bookings"]) >= 1
    detail_card = platform_client_detail(db, card_id=card.id)
    assert detail_card and detail_card["card"].id == card.id
    db.close()


def test_booking_status_change():
    db = _session()
    _c, _cal, _u, _card, b1 = _seed_consultant(db)
    booking, err = admin_set_booking_status(db, b1.id, "confirmed", notify=False)
    assert err is None
    assert booking and booking.status == "confirmed"
    listed = list_bookings(db, status="confirmed")
    assert any(b.id == b1.id for b in listed)
    db.close()


def test_calendar_disable_and_security_logins():
    db = _session()
    c, cal, _u, _card, _b1 = _seed_consultant(db)
    rows = list_calendars(db, consultant_id=c.id)
    assert any(r["calendar"].id == cal.id for r in rows)
    updated = set_calendar_active(db, cal.id, is_active=False)
    assert updated and updated.is_active is False
    write_admin_audit(
        db,
        actor_user_id=None,
        action="login_failed",
        entity="user",
        payload={"email": "x@t.c"},
    )
    db.commit()
    failed = list_failed_logins(db)
    assert any(f.action == "login_failed" for f in failed)
    db.close()
