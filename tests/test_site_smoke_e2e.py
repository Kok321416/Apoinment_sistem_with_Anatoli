"""E2E smoke: public specialist link + cabinet auth gates (no live MySQL)."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_async_db
from app.models import Calendar, Category, Consultant, Service, User


@pytest.fixture()
def public_client(tmp_path):
    from app.main import app

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            try:
                await conn.execute(text("ALTER TABLE consultants ADD COLUMN public_slug VARCHAR(64)"))
            except Exception:
                pass

        async with session_factory() as db:
            cat = Category(name_category="Общая")
            db.add(cat)
            await db.flush()
            user = User(
                username="spec@test.com",
                email="spec@test.com",
                password="x",
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            db.add(user)
            await db.flush()
            consultant = Consultant(
                first_name="Артем",
                last_name="Тестов",
                email="spec@test.com",
                phone="+79990001122",
                category_of_specialist_id=cat.id,
                user_id=user.id,
            )
            db.add(consultant)
            await db.flush()
            await db.execute(
                text("UPDATE consultants SET public_slug = :slug WHERE id = :id"),
                {"slug": "spec", "id": consultant.id},
            )
            cal = Calendar(
                consultant_id=consultant.id,
                name="Основной",
                color="#111111",
                is_active=True,
            )
            db.add(cal)
            await db.flush()
            db.add(
                Service(
                    consultant_id=consultant.id,
                    calendar_id=cal.id,
                    name="Консультация",
                    duration_minutes=60,
                    is_active=True,
                )
            )
            await db.commit()
            return consultant.id, cal.id

    import asyncio

    consultant_id, calendar_id = asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db
    client = TestClient(app)
    try:
        yield client, consultant_id, calendar_id
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_public_specialist_page_open_without_login(public_client):
    client, _cid, _cal_id = public_client
    r = client.get("/s/spec/", follow_redirects=False)
    assert r.status_code == 200, r.text[:500]
    assert "Артем" in r.text
    assert "Календари" in r.text or "календар" in r.text.lower()
    assert "Войти для записи" in r.text or "welcome" in r.text.lower()
    assert "Почему выбирают" not in r.text
    assert "/s/spec/welcome/" not in (r.headers.get("location") or "")


def test_public_specialist_booking_still_requires_gate(public_client):
    client, _cid, cal_id = public_client
    r = client.get(f"/s/spec/c/{cal_id}/", follow_redirects=False)
    assert r.status_code in (302, 303)
    loc = r.headers.get("location") or ""
    assert "/s/spec/welcome/" in loc


def test_cabinet_routes_redirect_anonymous_to_login():
    from app.main import app

    client = TestClient(app)
    for path in (
        "/dashboard/",
        "/manage/",
        "/clients/",
        "/booking/",
        "/profile/",
        "/integrations/",
        "/calendars/",
        "/services/",
        "/become-specialist/",
    ):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (302, 303), path
        loc = (r.headers.get("location") or "").lower()
        assert "login" in loc or "accounts" in loc, f"{path} -> {loc}"

    # Client cabinet removed — legacy routes redirect home.
    for path in ("/my-bookings/", "/diagnostics/"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (302, 303)
        assert (r.headers.get("location") or "").rstrip("/") in ("/", "")


def test_public_routes_respond():
    from app.main import app

    client = TestClient(app)
    for path in ("/", "/login/", "/register/", "/tg/", "/guide/", "/apps/", "/privacy/", "/terms/", "/health"):
        r = client.get(path, follow_redirects=True)
        assert r.status_code == 200, f"{path} => {r.status_code}"


def test_health_mini_app_endpoint():
    from app.main import app

    client = TestClient(app)
    r = client.get("/health/mini-app")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "assets" in body
