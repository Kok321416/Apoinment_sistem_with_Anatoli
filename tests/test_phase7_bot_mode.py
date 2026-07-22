"""Phase 7 telegram capabilities / ui-mode."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Booking, Calendar, Category, Consultant, Integration, SocialAccount, User
from app.services.telegram_capabilities import resolve_capabilities, set_ui_mode


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_dual_needs_picker_until_mode_saved():
    db = _session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    user = User(username="d", password="x", email="d@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="d@t.c",
        phone="+7999",
        category_of_specialist_id=cat.id,
        user_id=user.id,
    )
    db.add(c)
    db.flush()
    db.add(
        Integration(
            consultant_id=c.id,
            telegram_chat_id="555100",
            telegram_connected=True,
            telegram_enabled=True,
        )
    )
    db.add(SocialAccount(provider="telegram", uid="555100", user_id=user.id, extra_data="{}"))
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()
    from datetime import date, time

    db.add(
        Booking(
            service_id=1,
            calendar_id=cal.id,
            client_name="X",
            client_phone="+1",
            booking_date=date.today(),
            booking_time=time(10, 0),
            status="pending",
            telegram_id=555100,
        )
    )
    db.commit()

    caps = resolve_capabilities(db, telegram_id=555100, telegram_chat_id="555100")
    assert caps["dual"] is True
    assert caps["needs_picker"] is True

    ok, _ = set_ui_mode(db, "555100", "specialist")
    assert ok
    caps2 = resolve_capabilities(db, telegram_id=555100, telegram_chat_id="555100")
    assert caps2["needs_picker"] is False
    assert caps2["mode"] == "specialist"
    db.close()


def test_client_only_defaults_client_mode():
    db = _session()
    caps = resolve_capabilities(db, telegram_id=42, telegram_chat_id="42")
    assert caps["is_client"] is True
    assert caps["is_specialist"] is False
    assert caps["mode"] == "client"
    db.close()
