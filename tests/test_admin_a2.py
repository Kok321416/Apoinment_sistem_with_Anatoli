"""Admin A2: KPI, user search, errors."""
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, PlatformErrorLog, User
from app.services.platform_admin_users import dashboard_kpi, search_users, user_admin_card
from app.services.platform_errors import list_errors, record_platform_error, set_error_status


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_dashboard_kpi_counts():
    db = _session()
    u = User(username="a@t.c", password="x", email="a@t.c", date_joined=datetime.now())
    db.add(u)
    db.flush()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="a@t.c",
        phone="+1",
        category_of_specialist_id=cat.id,
        user_id=u.id,
    )
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()
    db.add(
        Booking(
            service_id=1,
            calendar_id=cal.id,
            client_name="X",
            client_phone="1",
            booking_date=date.today(),
            booking_time=datetime.now().time().replace(microsecond=0),
            status="pending",
        )
    )
    db.add(PlatformErrorLog(status="new", message="boom", path="/x"))
    db.commit()
    kpi = dashboard_kpi(db)
    assert kpi["users_total"] >= 1
    assert kpi["consultants_total"] >= 1
    assert kpi["bookings_today"] >= 1
    assert kpi["errors_new"] >= 1
    db.close()


def test_search_users_by_email_and_id():
    db = _session()
    u = User(
        username="findme@t.c",
        password="x",
        email="findme@t.c",
        first_name="Find",
        last_name="Me",
        date_joined=datetime.now(),
    )
    db.add(u)
    db.commit()
    rows = search_users(db, "findme")
    assert any(r.id == u.id for r in rows)
    rows2 = search_users(db, str(u.id))
    assert any(r.id == u.id for r in rows2)
    card = user_admin_card(db, u.id)
    assert card and card["user"].id == u.id
    db.close()


def test_error_status_lifecycle():
    db = _session()
    record_platform_error(path="/fail", method="GET", status_code=500, message="x")
    # record uses own SessionLocal - won't hit our memory db.
    # Use direct model instead:
    row = PlatformErrorLog(status="new", message="x", path="/fail")
    db.add(row)
    db.commit()
    updated = set_error_status(db, row.id, "fixed")
    assert updated is not None
    assert updated.status == "fixed"
    listed = list_errors(db, status="fixed")
    assert any(e.id == row.id for e in listed)
    db.close()


def test_impersonation_session_helpers():
    from app.auth.session import get_impersonator_id, start_impersonation, stop_impersonation
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
    start_impersonation(request, admin_user_id=1, target_user_id=99)
    assert request.session["user_id"] == 99
    assert get_impersonator_id(request) == 1
    stop_impersonation(request)
    assert request.session["user_id"] == 1
    assert get_impersonator_id(request) is None
