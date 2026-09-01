"""E2E: profile-scoped diagnostics (/s/{slug}/diagnostics/)."""
from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.passwords import hash_password
from app.database import Base, get_async_db
from app.diagnostics.catalog import BHS, get_test
from app.models import Calendar, Category, Consultant, Service, User


@pytest.fixture()
def diagnostics_client(tmp_path):
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
            spec_user = User(
                username="spec@test.com",
                email="spec@test.com",
                password=hash_password("specpass"),
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            client_user = User(
                username="+79991234567",
                email="",
                password=hash_password("clientpass"),
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            db.add(spec_user)
            db.add(client_user)
            await db.flush()
            consultant = Consultant(
                first_name="Артем",
                last_name="Тестов",
                email="spec@test.com",
                phone="+79990001122",
                category_of_specialist_id=cat.id,
                user_id=spec_user.id,
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
            return consultant.id, client_user.id

    import asyncio

    consultant_id, client_user_id = asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db

    import app.database as database_module

    database_module._async_engine = engine
    database_module._AsyncSessionLocal = session_factory

    client = TestClient(app)
    try:
        yield client, consultant_id, client_user_id
    finally:
        app.dependency_overrides.clear()
        database_module._async_engine = None
        database_module._AsyncSessionLocal = None
        asyncio.run(engine.dispose())


def _login_client(client: TestClient, phone: str = "+79991234567", password: str = "clientpass"):
    r = client.get("/login/", follow_redirects=True)
    assert r.status_code == 200, r.text[:300]
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    assert m, "csrf_token missing on login page"
    csrf = m.group(1)
    return client.post(
        "/login/",
        data={"login": phone, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


def test_diagnostics_requires_login(diagnostics_client):
    client, _cid, _uid = diagnostics_client
    r = client.get("/s/spec/diagnostics/", follow_redirects=False)
    assert r.status_code == 302
    assert "/s/spec/welcome/" in (r.headers.get("location") or "")


def test_diagnostics_hub_and_submit_bhs(diagnostics_client):
    client, _cid, _uid = diagnostics_client
    login_r = _login_client(client)
    assert login_r.status_code == 302, login_r.text[:300]

    hub = client.get("/s/spec/diagnostics/", follow_redirects=True)
    assert hub.status_code == 200, hub.text[:500]
    assert "Диагностика" in hub.text
    assert BHS.title in hub.text

    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/", follow_redirects=True)
    assert take.status_code == 200, take.text[:500]
    assert "Завершить и посмотреть результат" in take.text

    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m, "csrf_token missing on take page"
    csrf = m.group(1)

    test = get_test(BHS.code)
    assert test and test.runnable
    data = {"csrf_token": csrf, "source": "profile"}
    for item in test.items:
        data[item.id] = str(item.options[0][1])

    submit = client.post(
        f"/s/spec/diagnostics/tests/{BHS.code}/submit/",
        data=data,
        follow_redirects=False,
    )
    assert submit.status_code == 302, submit.text[:500]
    loc = submit.headers.get("location") or ""
    assert "/s/spec/diagnostics/results/" in loc, f"unexpected redirect: {loc}"

    result = client.get(loc, follow_redirects=True)
    assert result.status_code == 200, result.text[:500]
    assert "Безнадёжность" in result.text or "безнад" in result.text.lower()

    hub2 = client.get("/s/spec/diagnostics/", follow_redirects=True)
    assert hub2.status_code == 200
    assert "История результатов" in hub2.text
    assert "Полная расшифровка" in hub2.text or BHS.title in hub2.text
