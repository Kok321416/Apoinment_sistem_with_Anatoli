"""Phase 8 Mini App hub: initData auth + hub-state session flow."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_async_db
from app.models import Category, Consultant, SocialAccount, User
from app.services.telegram_webapp_auth import find_or_create_user_from_webapp, validate_webapp_init_data


def _sign_init_data(bot_token: str, fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    pairs = dict(fields)
    pairs["hash"] = digest
    return urlencode(pairs)


def test_validate_webapp_init_data_ok_and_bad():
    token = "123456:ABC-DEF"
    user = {"id": 777001, "first_name": "Ada", "username": "ada"}
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user, separators=(",", ":")),
    }
    init_data = _sign_init_data(token, fields)
    parsed = validate_webapp_init_data(init_data, bot_token=token)
    assert parsed is not None
    assert parsed["user"]["id"] == 777001

    bad = init_data[:-4] + "dead"
    assert validate_webapp_init_data(bad, bot_token=token) is None


def test_validate_webapp_init_data_expired():
    token = "123456:ABC-DEF"
    user = {"id": 1, "first_name": "Old"}
    fields = {
        "auth_date": str(int(time.time()) - 86400 * 2),
        "user": json.dumps(user, separators=(",", ":")),
    }
    init_data = _sign_init_data(token, fields)
    assert validate_webapp_init_data(init_data, bot_token=token) is None


def test_find_or_create_user_from_webapp_creates_client_only():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = find_or_create_user_from_webapp(
        db,
        {"id": 555200, "first_name": "Bob", "username": "bob"},
    )
    assert user is not None
    assert user.username == "telegram_555200"
    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.provider == "telegram", SocialAccount.uid == "555200")
        .first()
    )
    assert sa is not None
    assert db.query(Consultant).filter(Consultant.user_id == user.id).first() is None

    again = find_or_create_user_from_webapp(db, {"id": 555200, "first_name": "Bob"})
    assert again.id == user.id
    db.close()


@pytest.fixture()
def mini_app_client(monkeypatch):
    from types import SimpleNamespace

    from app.main import app

    token = "999888:TEST-TOKEN"
    monkeypatch.setattr(
        "app.services.telegram_webapp_auth.get_settings",
        lambda: SimpleNamespace(telegram_bot_token=token),
    )

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db

    import app.database as database_module

    database_module._async_engine = engine
    database_module._AsyncSessionLocal = session_factory

    client = TestClient(app)
    try:
        yield client, session_factory, token
    finally:
        app.dependency_overrides.clear()
        database_module._async_engine = None
        database_module._AsyncSessionLocal = None
        asyncio.run(engine.dispose())


def _signed_init_data(token: str, tg_id: int = 424242, username: str = "cara") -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(
            {"id": tg_id, "first_name": "Cara", "username": username},
            separators=(",", ":"),
        ),
    }
    return _sign_init_data(token, fields)


def test_webapp_auth_api_sets_session_and_hub_state(mini_app_client):
    client, session_factory, token = mini_app_client
    init_data = _signed_init_data(token)

    hub0 = client.get("/api/telegram/hub-state")
    assert hub0.status_code == 200
    assert hub0.json().get("authenticated") is False

    r = client.post("/api/auth/telegram", json={"init_data": init_data, "mode": "client"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert body.get("has_consultant") is False

    hub1 = client.get("/api/telegram/hub-state")
    assert hub1.status_code == 200
    state = hub1.json()
    assert state.get("authenticated") is True
    assert state.get("has_consultant") is False
    assert state.get("mode") == "client"
    assert state.get("hub_available") is False
    assert state.get("reason") == "specialist_access_required"
    assert state.get("role") == "client"

    async def _add_consultant():
        async with session_factory() as db:
            cat = Category(name_category="Общая")
            db.add(cat)
            await db.flush()
            result = await db.execute(select(User).where(User.username == "telegram_424242"))
            user = result.scalar_one()
            db.add(
                Consultant(
                    first_name="C",
                    last_name="A",
                    email=user.email,
                    phone="+7000",
                    category_of_specialist_id=cat.id,
                    user_id=user.id,
                )
            )
            await db.commit()

    asyncio.run(_add_consultant())

    r2 = client.post(
        "/api/telegram/webapp-auth",
        json={"init_data": init_data, "mode": "specialist"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("has_consultant") is True
    assert r2.json().get("access_token")

    hub2 = client.get("/api/telegram/hub-state?mode=specialist")
    assert hub2.status_code == 200
    state2 = hub2.json()
    assert state2.get("authenticated") is True
    assert state2.get("has_consultant") is True
    assert state2.get("mode") == "specialist"
    assert state2.get("hub_available") is True
    assert state2.get("role") == "specialist"


def test_webapp_auth_rejects_invalid_init_data(mini_app_client):
    client, _session_factory, token = mini_app_client
    init_data = _signed_init_data(token)[:-4] + "dead"
    r = client.post("/api/telegram/webapp-auth", json={"init_data": init_data})
    assert r.status_code == 401
    assert r.json().get("success") is False

    hub = client.get("/api/telegram/hub-state")
    assert hub.json().get("authenticated") is False


def test_webapp_auth_rejects_missing_init_data(mini_app_client):
    client, _session_factory, _token = mini_app_client
    r = client.post("/api/telegram/webapp-auth", json={"init_data": ""})
    assert r.status_code == 401
    assert r.json().get("success") is False


def test_webapp_auth_creates_new_telegram_user(mini_app_client):
    client, session_factory, token = mini_app_client
    init_data = _signed_init_data(token, tg_id=900001, username="newtg")
    r = client.post("/api/telegram/webapp-auth", json={"init_data": init_data})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert body.get("has_consultant") is False

    hub = client.get("/api/telegram/hub-state")
    assert hub.json().get("authenticated") is True
    assert hub.json().get("mode") == "client"

    async def _check_user():
        from sqlalchemy import select

        async with session_factory() as db:
            user = (await db.execute(select(User).where(User.username == "telegram_900001"))).scalar_one_or_none()
            assert user is not None
            consultant = (
                await db.execute(select(Consultant).where(Consultant.user_id == user.id))
            ).scalar_one_or_none()
            assert consultant is None

    asyncio.run(_check_user())


def test_webapp_auth_without_session_cookie_is_unauthenticated(mini_app_client):
    """Simulates lost cookie: new TestClient has no session after auth on another client."""
    client_a, _session_factory, token = mini_app_client
    init_data = _signed_init_data(token, tg_id=900002, username="lostcookie")
    assert client_a.post("/api/telegram/webapp-auth", json={"init_data": init_data}).status_code == 200

    from app.main import app

    client_b = TestClient(app)
    hub = client_b.get("/api/telegram/hub-state")
    assert hub.json().get("authenticated") is False


def test_tg_hub_serves_webapp_boot_v26(mini_app_client):
    client, _session_factory, _token = mini_app_client
    r = client.get("/tg/")
    assert r.status_code == 200
    assert r.status_code != 302
    loc = r.headers.get("location") or ""
    assert "t.me" not in loc
    assert "telegram-webapp.js?v=26" in r.text
    assert 'id="tg-hub-authed"' in r.text
    assert 'id="tg-hub-guest"' in r.text
    assert 'id="tg-hub-error"' in r.text


def test_webapp_auth_idempotent_and_bearer_without_cookie(mini_app_client):
    client, _session_factory, token = mini_app_client
    init_data = _signed_init_data(token, tg_id=900010, username="bearer")
    r1 = client.post("/api/auth/telegram", json={"init_data": init_data})
    r2 = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r1.status_code == 200 and r2.status_code == 200
    access = r1.json().get("access_token")
    assert access

    from app.main import app

    client_b = TestClient(app)
    denied = client_b.get("/api/telegram/hub-state")
    assert denied.json().get("authenticated") is False
    hub = client_b.get("/api/telegram/hub-state", headers={"Authorization": f"Bearer {access}"})
    assert hub.json().get("authenticated") is True
    me = client_b.get("/api/me", headers={"Authorization": f"Bearer {access}"})
    assert me.json().get("authenticated") is True


def test_tg_hub_does_not_use_async_db(mini_app_client):
    client, _session_factory, _token = mini_app_client
    from app.database import get_async_db
    from app.main import app

    async def _boom():
        raise AssertionError("GET /tg/ must not open the database")
        yield

    app.dependency_overrides[get_async_db] = _boom
    try:
        r = client.get("/tg/")
        assert r.status_code == 200
        assert "<!DOCTYPE html>" in r.text or "<html" in r.text.lower()
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_webapp_diag_accepts_no_init_data_kind(mini_app_client, monkeypatch):
    client, _session_factory, _token = mini_app_client
    recorded = []

    monkeypatch.setattr(
        "app.services.platform_errors.record_platform_error",
        lambda **k: recorded.append(k.get("message", "")),
    )
    monkeypatch.setattr("app.services.ops_alerts.notify_ops_alert", lambda **k: False)
    r = client.post(
        "/api/telegram/webapp-diag",
        json={"kind": "no_init_data", "path": "/tg/", "platform": "android", "extra": "empty initData"},
    )
    assert r.status_code == 200
    assert any("no_init_data" in msg for msg in recorded)
