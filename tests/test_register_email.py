"""Email registration flow tests."""
from __future__ import annotations

import asyncio
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_async_db


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token not found on page"
    return match.group(1)


@pytest.fixture()
def register_client(monkeypatch):
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

    asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db

    sent = []

    def fake_send(to_email: str, code: str) -> bool:
        sent.append((to_email, code))
        return True

    monkeypatch.setattr("app.services.email_verification.send_verification_email", fake_send)

    client = TestClient(app)
    try:
        yield client, sent
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_email_registration_does_not_500(register_client):
    client, sent = register_client
    email = f"reg_{uuid.uuid4().hex[:8]}@example.com"
    csrf = _csrf_from_html(client.get("/register/").text)

    response = client.post(
        "/register/",
        data={
            "csrf_token": csrf,
            "auth_method": "email",
            "fio": "Иванов Иван Иванович",
            "phone": "+79991234567",
            "email": email,
            "password": "TestPass123!",
            "password_confirm": "TestPass123!",
            "accept_privacy": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text[:1500]
    assert "/accounts/verify-email/" in response.headers.get("location", "")
    assert sent and sent[0][0] == email
