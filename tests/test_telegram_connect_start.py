"""Specialist Telegram notify connect: deep-link parse + bridge + Mini App API."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.passwords import hash_password
from app.database import (
    Base,
    configure_async_sessionmaker,
    get_async_db,
    reset_async_sessionmaker,
)
from app.models import Category, Consultant, Integration, User
from bot.handlers.commands import _start_arg


def _sign_init_data(bot_token: str, fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    pairs = dict(fields)
    pairs["hash"] = digest
    return urlencode(pairs)


def test_start_arg_from_command_object():
    msg = SimpleNamespace(text="/start")
    cmd = SimpleNamespace(args="connect_spec_abc123")
    assert _start_arg(msg, cmd) == "connect_spec_abc123"


def test_start_arg_fallback_from_message_text():
    msg = SimpleNamespace(text="/start@all_for_clients_bot connect_spec_deadbeef")
    cmd = SimpleNamespace(args=None)
    assert _start_arg(msg, cmd) == "connect_spec_deadbeef"


def test_start_arg_empty():
    msg = SimpleNamespace(text="/start")
    cmd = SimpleNamespace(args="")
    assert _start_arg(msg, cmd) == ""


@pytest.fixture()
def connect_client(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    from app.config import Settings, get_settings

    monkeypatch.setattr(Settings, "telegram_bot_username", "all_for_clients_bot")
    monkeypatch.setattr(Settings, "telegram_bot_token", "123456:TEST-TOKEN-CONNECT")
    get_settings.cache_clear()

    async def _no_push(*_a, **_k):
        return False

    monkeypatch.setattr("app.services.telegram.send_telegram_await", _no_push)

    from app.main import app
    import app.routers.pages as pages_mod
    import app.routers.api as api_mod

    pages_mod.settings = get_settings()
    api_mod.settings = get_settings()

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            cat = Category(name_category="Общая")
            db.add(cat)
            await db.flush()
            user = User(
                username="tg-connect@test.com",
                email="tg-connect@test.com",
                password=hash_password("specpass"),
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            db.add(user)
            await db.flush()
            consultant = Consultant(
                first_name="Тг",
                last_name="Коннект",
                email="tg-connect@test.com",
                phone="+79990001133",
                category_of_specialist_id=cat.id,
                user_id=user.id,
            )
            db.add(consultant)
            await db.flush()
            db.add(Integration(consultant_id=consultant.id, telegram_enabled=True))
            await db.commit()

    import asyncio

    asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db
    configure_async_sessionmaker(session_factory, async_engine=engine)

    client = TestClient(app)
    try:
        yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        reset_async_sessionmaker()
        get_settings.cache_clear()
        asyncio.run(engine.dispose())

def _login(client: TestClient):
    r = client.get("/login/")
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    assert tok
    client.post(
        "/login/",
        data={"login": "tg-connect@test.com", "password": "specpass", "csrf_token": tok.group(1)},
        follow_redirects=True,
    )


def test_connect_app_serves_bridge_not_bare_redirect(connect_client):
    client, _sf = connect_client
    _login(client)
    r = client.get("/integrations/telegram/connect-app/", follow_redirects=False)
    assert r.status_code == 200, r.text[:400]
    assert "connect-bridge" in r.text
    assert "connect_spec_" in r.text
    assert "Открыть бота" in r.text
    assert "t.me/all_for_clients_bot?start=connect_spec_" in r.text


def test_connect_telegram_webapp_one_click(connect_client):
    client, session_factory = connect_client
    _login(client)
    page = client.get("/integrations/")
    csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
    assert csrf
    token = "123456:TEST-TOKEN-CONNECT"
    init_data = _sign_init_data(
        token,
        {
            "auth_date": str(int(time.time())),
            "user": json.dumps({"id": 9001001, "first_name": "Spec"}, separators=(",", ":")),
        },
    )
    r = client.post(
        "/api/specialist/connect-telegram-webapp",
        headers={"X-CSRF-Token": csrf.group(1)},
        json={"init_data": init_data, "csrf_token": csrf.group(1)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert body.get("chat_id") == "9001001"

    import asyncio

    async def _check():
        async with session_factory() as db:
            integ = (
                await db.execute(select(Integration).where(Integration.telegram_chat_id == "9001001"))
            ).scalar_one_or_none()
            assert integ is not None
            assert integ.telegram_connected is True

    asyncio.run(_check())
