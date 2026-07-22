"""Password reset and admin booking detail tests."""
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, PasswordResetToken, Service, User
from app.services.deploy_checklist import deploy_checklist
from app.services.password_reset import create_password_reset_token, get_valid_reset_token
from app.services.platform_admin_domain import booking_admin_card


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_password_reset_token_lifecycle():
    db = _session()
    u = User(username="u@t.c", password="x", email="u@t.c", date_joined=datetime.now())
    db.add(u)
    db.commit()
    row = create_password_reset_token(db, u)
    db.commit()
    found = get_valid_reset_token(db, row.token)
    assert found is not None
    assert found.user_id == u.id
    db.close()


def test_booking_admin_card():
    db = _session()
    cat = Category(name_category="X")
    db.add(cat)
    db.flush()
    c = Consultant(first_name="A", last_name="B", email="a@t.c", phone="1", category_of_specialist_id=cat.id)
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()
    svc = Service(consultant_id=c.id, calendar_id=cal.id, name="S", duration_minutes=60)
    db.add(svc)
    db.flush()
    b = Booking(
        service_id=svc.id,
        calendar_id=cal.id,
        client_name="X",
        client_phone="1",
        booking_date=date.today(),
        booking_time=time(10, 0),
        status="pending",
    )
    db.add(b)
    db.commit()
    card = booking_admin_card(db, b.id)
    assert card and card["booking"].id == b.id
    db.close()


def test_deploy_checklist_returns_items():
    db = _session()
    items = deploy_checklist(db)
    assert len(items) >= 5
    assert any(i["id"] == "test_self" for i in items)
    db.close()
