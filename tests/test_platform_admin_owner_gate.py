"""Owner allowlist gate for /platform-admin/."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth.session import AuthUser
from app.config import get_settings
from app.deps import _platform_admin_allowed, require_platform_admin_async


def _user(**kwargs) -> AuthUser:
    base = dict(
        id=1,
        username="owner",
        email="kok321416x@yandex.ru",
        first_name="",
        last_name="",
        is_active=True,
        password_hash="x",
        is_staff=True,
        is_superuser=True,
    )
    base.update(kwargs)
    return AuthUser(**base)


def test_owner_allowlist_blocks_other_staff(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_admin_owner_emails", "kok321416x@yandex.ru")
    assert _platform_admin_allowed(_user()) is True
    assert _platform_admin_allowed(_user(email="other@example.com", username="other", is_superuser=True)) is False
    assert _platform_admin_allowed(_user(email="kok321416x@yandex.ru", is_staff=False, is_superuser=False)) is False


def test_empty_allowlist_denies_everyone(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_admin_owner_emails", "")
    assert _platform_admin_allowed(_user()) is False


def test_require_platform_admin_async_owner_only(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_admin_enabled", True)
    monkeypatch.setattr(settings, "platform_admin_owner_emails", "kok321416x@yandex.ru")

    req = MagicMock()
    owner = _user()
    other = _user(email="staff@t.c", username="staff1")

    async def _run(user):
        async def fake_get(_request, _db):
            return user

        monkeypatch.setattr("app.auth.session.get_current_user_async", fake_get)
        return await require_platform_admin_async(req, MagicMock())

    assert asyncio.run(_run(owner)).email == owner.email
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_run(other))
    assert ei.value.status_code == 403


def test_platform_admin_disabled_returns_404(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_admin_enabled", False)
    monkeypatch.setattr(settings, "platform_admin_owner_emails", "kok321416x@yandex.ru")

    async def fake_get(_request, _db):
        return _user()

    monkeypatch.setattr("app.auth.session.get_current_user_async", fake_get)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(require_platform_admin_async(MagicMock(), MagicMock()))
    assert ei.value.status_code == 404
