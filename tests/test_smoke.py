"""Smoke tests — no live DB required for pure helpers."""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_db


def test_specialist_slug_for():
    from app.services.public_client import specialist_slug_for

    c = SimpleNamespace(id=42)
    assert specialist_slug_for(c) == "id-42"


def test_resolve_consultant_by_id_slug():
    from app.services.public_client import resolve_consultant_by_slug

    found = SimpleNamespace(id=7)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = found
    db.execute.side_effect = Exception("no public_slug column")

    assert resolve_consultant_by_slug(db, "id-7") is found


def test_delete_calendar_blocks_when_services():
    from app.services.entity_delete import delete_calendar

    db = MagicMock()
    db.query.return_value.filter.return_value.count.side_effect = [0, 2]  # bookings, services
    cal = SimpleNamespace(id=1)
    ok, msg = delete_calendar(db, cal)
    assert ok is False
    assert "услуг" in msg.lower()


def test_delete_calendar_blocks_when_bookings():
    from app.services.entity_delete import delete_calendar

    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 3
    cal = SimpleNamespace(id=1)
    ok, msg = delete_calendar(db, cal)
    assert ok is False
    assert "запис" in msg.lower()


def test_reminder_copy_uses_hours():
    from app.services.telegram import format_reminder_message, format_specialist_reminder_message

    booking = SimpleNamespace(
        booking_time=time(10, 0),
        booking_end_time=time(11, 0),
        booking_date=date.today() + timedelta(days=1),
        service=SimpleNamespace(name="Консультация", duration_minutes=60),
        calendar=SimpleNamespace(name="Основной", consultant=SimpleNamespace(first_name="Иван", last_name="Петров", email="a@b.c")),
        client_name="Клиент",
        client_phone="+7000",
        client_telegram="",
        client_email="",
    )
    msg = format_reminder_message(booking, 6)
    assert "6" in msg
    assert "24 часа" not in msg
    spec = format_specialist_reminder_message(booking, 6)
    assert "6" in spec


def test_bot_api_rejects_raw_token_when_secret_set(monkeypatch):
    from app.security import bot_api

    class S:
        bot_api_secret = "secret-value"
        telegram_bot_token = "bot-token"

    monkeypatch.setattr(bot_api, "get_settings", lambda: S())
    req = MagicMock()
    req.headers = {"X-Bot-Token": "bot-token"}
    assert bot_api.verify_bot_request(req, b"{}") is False


def test_health_endpoint():
    from app.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "schema" in body


def test_yandex_redirect_uri(monkeypatch):
    from app.services import yandex_auth

    class S:
        site_url = "https://example.com"

    monkeypatch.setattr(yandex_auth, "get_settings", lambda: S())
    assert yandex_auth.yandex_redirect_uri() == "https://example.com/accounts/yandex/callback/"


def test_yandex_authorize_url_contains_client_id(monkeypatch):
    from app.services import yandex_auth

    class S:
        yandex_oauth_client_id = "test-client-id"
        yandex_oauth_client_secret = "secret"
        site_url = "https://example.com"

    monkeypatch.setattr(yandex_auth, "get_settings", lambda: S())
    url = yandex_auth.build_authorize_url("state-token")
    assert "client_id=test-client-id" in url
    assert "state=state-token" in url
    assert "oauth.yandex.ru/authorize" in url


def test_normalize_phone_fits_db_column():
    from app.deps import normalize_phone

    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"
    assert len(normalize_phone("+7 (999) 123-45-67")) <= 15


def test_yandex_signup_creates_consultant():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401 — register metadata
    from app.database import Base
    from app.models import Consultant, SocialAccount, User
    from app.services.yandex_auth import complete_yandex_oauth

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    profile = {
        "id": 12345,
        "login": "testuser",
        "first_name": "Иван",
        "last_name": "Иванов",
        "display_name": "Иван Иванов",
        "default_email": "ivan@yandex.ru",
    }
    user, err = complete_yandex_oauth(
        db,
        process="signup",
        profile=profile,
        register_fio="Иванов Иван Петрович",
        register_phone="+7 (999) 123-45-67",
        connect_user_id=None,
    )
    assert err is None
    assert user is not None
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).one()
    assert consultant.phone == "+79991234567"
    assert len(consultant.phone) <= 15
    assert db.query(SocialAccount).filter(SocialAccount.provider == "yandex").count() == 1
    db.close()


def test_blank_field_hides_none_string():
    from app.deps import blank_field

    assert blank_field(None) == ""
    assert blank_field("None") == ""
    assert blank_field("  null  ") == ""
    assert blank_field("https://vk.com/user") == "https://vk.com/user"


def test_yandex_login_redirects_to_register_without_signup_data(monkeypatch):
    from app.main import app
    from app.routers import oauth as oauth_router

    monkeypatch.setattr(oauth_router, "yandex_oauth_configured", lambda: True)
    client = TestClient(app)
    r = client.get("/accounts/yandex/login/?process=signup", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/register/?error=yandex_signup"


def test_clear_day_slots_detaches_bookings():
    from datetime import date, time

    from app.models import Booking, Calendar, Service, TimeSlot
    from app.services.calendar_schedule import clear_day_slots, copy_day_slots, preset_fulltime

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cal = Calendar(consultant_id=1, name="C", color="#7d5cff")
    db.add(cal)
    db.flush()
    slot = TimeSlot(
        calendar_id=cal.id,
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(17, 0),
    )
    db.add(slot)
    db.flush()
    svc = Service(consultant_id=1, calendar_id=cal.id, name="S", duration_minutes=60)
    db.add(svc)
    db.flush()
    booking = Booking(
        service_id=svc.id,
        time_slot_id=slot.id,
        calendar_id=cal.id,
        client_name="Клиент",
        client_phone="79991234567",
        booking_date=date(2026, 8, 1),
        booking_time=time(10, 0),
        status="confirmed",
    )
    db.add(booking)
    db.commit()

    assert clear_day_slots(db, cal.id, 0) == 1
    db.commit()
    db.refresh(booking)
    assert booking.time_slot_id is None
    assert db.query(TimeSlot).filter(TimeSlot.calendar_id == cal.id).count() == 0

    slot2 = TimeSlot(
        calendar_id=cal.id,
        day_of_week=1,
        start_time=time(10, 0),
        end_time=time(12, 0),
    )
    db.add(slot2)
    db.commit()
    assert copy_day_slots(db, cal, 1, [2], replace=True) == 1
    db.commit()
    assert preset_fulltime(db, cal, [3]) == 1
    db.commit()
    db.close()


def test_new_api_routes_require_auth():
    from app.main import app

    client = TestClient(app)
    for path in ("/services/catalog", "/profile/data", "/calendars/1/schedule"):
        assert client.get(path).status_code == 401


def test_calendar_schedule_slot_position():
    from app.services.calendar_schedule import slot_position

    top, height = slot_position(time(9, 30), time(15, 0))
    assert 39.0 < top < 40.0
    assert 22.0 < height < 24.0


def test_profile_completeness_empty_consultant():
    from app.models import Category, Consultant
    from app.services.profile_hub import completeness

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cat = Category(name_category="Психолог")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="",
        last_name="",
        email="a@b.c",
        phone="",
        category_of_specialist_id=cat.id,
    )
    db.add(c)
    db.flush()
    result = completeness(c, db, c.id)
    assert result["percent"] == 0
    assert len(result["checks"]) == 8
    assert any(not ch["done"] for ch in result["checks"])
    db.close()


def test_profile_completeness_basic_fields():
    from app.models import Calendar, Category, Consultant, Service
    from app.services.profile_hub import compute_completeness

    result = compute_completeness(
        first_name="Иван",
        last_name="Петров",
        email="ivan@example.com",
        phone="+79991234567",
        profile_description="Короткое описание специалиста для клиентов.",
        video_link="",
        has_photo=True,
        social_count=1,
        services_active=1,
        services_total=2,
        calendars_active=1,
        calendars_total=1,
    )
    assert result["percent"] == 78
    assert result["checks"][0]["done"] is True
    assert result["checks"][2]["done"] is True
    assert result["checks"][3]["partial"] is True
    assert result["checks"][5]["partial"] is True

def test_calendars_query_after_schema_patch():
    from sqlalchemy import text

    from app.db_schema import ensure_app_schema
    from app.models import Calendar
    import app.db_schema as schema_mod

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE calendars DROP COLUMN disabled_weekdays"))
        conn.execute(text(
            "INSERT INTO calendars (consultant_id, name, color, is_active, created_at, updated_at, "
            "break_between_services_minutes, book_ahead_hours, max_services_per_day, "
            "reminder_hours_first, reminder_hours_second) "
            "VALUES (1, 'Main', '#7d5cff', 1, datetime('now'), datetime('now'), 0, 24, 0, 24, 1)"
        ))

    old_engine = schema_mod.engine
    old_attempted = schema_mod._SCHEMA_PATCHES_ATTEMPTED
    try:
        schema_mod.engine = engine
        schema_mod._SCHEMA_PATCHES_ATTEMPTED = False
        ensure_app_schema()
        db = sessionmaker(bind=engine)()
        calendars = db.query(Calendar).all()
        assert len(calendars) == 1
        assert calendars[0].name == "Main"
        assert calendars[0].disabled_weekdays == ""
        db.close()
    finally:
        schema_mod.engine = old_engine
        schema_mod._SCHEMA_PATCHES_ATTEMPTED = old_attempted


def test_schema_patch_adds_disabled_weekdays():
    from sqlalchemy import inspect, text

    from app.db_schema import ensure_app_schema
    import app.db_schema as schema_mod

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE calendars DROP COLUMN disabled_weekdays"))

    old_engine = schema_mod.engine
    old_attempted = schema_mod._SCHEMA_PATCHES_ATTEMPTED
    try:
        schema_mod.engine = engine
        schema_mod._SCHEMA_PATCHES_ATTEMPTED = False
        ensure_app_schema()
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("calendars")}
        assert "disabled_weekdays" in cols
    finally:
        schema_mod.engine = old_engine
        schema_mod._SCHEMA_PATCHES_ATTEMPTED = old_attempted


def test_services_catalog_dashboard():
    from app.models import Calendar, Category, Consultant, Service
    from app.services.services_catalog import build_catalog_payload

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="s@b.c",
        phone="+79990000000",
        category_of_specialist_id=cat.id,
    )
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()
    db.add(Service(consultant_id=c.id, calendar_id=cal.id, name="Svc", duration_minutes=60, is_active=True))
    db.commit()
    payload = build_catalog_payload(db, c.id)
    assert payload["dashboard"]["total"] == 1
    assert payload["dashboard"]["active"] == 1
    assert len(payload["services"]) == 1
    assert payload["dashboard"]["calendars_total"] == 1
    db.close()


def test_clients_crm_completeness():
    from datetime import datetime

    from app.models import ClientCard
    from app.services.clients_crm import card_completeness

    card = ClientCard(
        consultant_id=1,
        name="Марина",
        phone="+7999",
        email="m@test.com",
    )
    card.id = 1
    card.created_at = datetime.utcnow()
    card.updated_at = datetime.utcnow()
    result = card_completeness(card)
    assert result["percent"] >= 70
    assert any(not c["done"] for c in result["checks"])


def test_disabled_weekday_blocks_slots():
    from app.models import Calendar
    from app.services.calendar_schedule import set_day_working
    from app.services.slots import get_available_slots

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cal = Calendar(consultant_id=1, name="C", color="#7d5cff")
    db.add(cal)
    db.flush()
    set_day_working(cal, date.today().weekday(), False)
    db.commit()
    svc = SimpleNamespace(duration_minutes=60)
    result = get_available_slots(db, cal, svc, date.today())
    assert result["available_slots"] == []
    db.close()


def test_services_schema_patch_legacy_table():
    from sqlalchemy import text

    from app.db_schema import _add_column, _column_exists
    import app.db_schema as schema_mod

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE services ("
                "id INTEGER PRIMARY KEY, consultant_id INTEGER, name VARCHAR(255), "
                "description TEXT, duration_minutes INTEGER DEFAULT 60, "
                "price NUMERIC(10,2), is_active BOOLEAN DEFAULT 1)"
            )
        )

    old_engine = schema_mod.engine
    try:
        schema_mod.engine = engine
        for column, ddl in (
            ("calendar_id", "INTEGER NULL"),
            ("color", "VARCHAR(7) NOT NULL DEFAULT '#7d5cff'"),
            ("icon", "VARCHAR(50) NULL"),
            ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
            ("created_at", "DATETIME NULL"),
            ("updated_at", "DATETIME NULL"),
        ):
            _add_column("services", column, ddl)
            assert _column_exists("services", column)
    finally:
        schema_mod.engine = old_engine


def test_services_page_renders_without_db_catalog_query(monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth.session import AuthUser
    from app.main import app
    from app.routers import pages as pages_router

    client = TestClient(app)
    user = AuthUser(
        id=1,
        username="u@test.com",
        email="u@test.com",
        first_name="A",
        last_name="B",
        is_active=True,
        password_hash="hash",
    )
    consultant = SimpleNamespace(id=10)

    monkeypatch.setattr(pages_router, "_require_user", lambda request, db: user)
    monkeypatch.setattr(pages_router, "get_consultant", lambda db, u: consultant)

    response = client.get("/services/")
    assert response.status_code == 200
    assert "services-page" in response.text


def test_booking_page_renders_with_empty_calendars(monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth.session import AuthUser
    from app.database import Base, get_db
    from app.main import app
    from app.models import Category, Consultant, User
    from app.auth.passwords import hash_password
    from app.routers import pages as pages_router

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    db = TestingSession()
    cat = Category(name_category="T")
    db.add(cat)
    db.flush()
    user_model = User(
        username="u@test.com",
        email="u@test.com",
        password=hash_password("pass"),
        is_active=True,
    )
    db.add(user_model)
    db.flush()
    consultant = Consultant(
        first_name="A",
        last_name="B",
        email="u@test.com",
        phone="+7",
        category_of_specialist_id=cat.id,
        user_id=user_model.id,
    )
    db.add(consultant)
    db.commit()
    consultant_id = consultant.id
    user_id = user_model.id
    db.close()

    auth_user = AuthUser(
        id=user_id,
        username="u@test.com",
        email="u@test.com",
        first_name="A",
        last_name="B",
        is_active=True,
        password_hash="hash",
    )
    monkeypatch.setattr(pages_router, "_require_user", lambda request, db: auth_user)
    monkeypatch.setattr(
        pages_router,
        "get_consultant",
        lambda db, u: SimpleNamespace(id=consultant_id),
    )

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        response = client.get("/booking/")
        assert response.status_code == 200
        assert "bookingPageContainer" in response.text
    finally:
        app.dependency_overrides.clear()
