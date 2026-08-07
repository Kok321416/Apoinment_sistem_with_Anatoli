"""Smoke checks for aiogram webhook path (no live Telegram / full app)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def webhook_secret(monkeypatch):
    secret = "test-webhook-secret-xyz"
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TESTTOKEN")
    from app.config import get_settings
    from bot.config import get_bot_settings

    get_settings.cache_clear()
    get_bot_settings.cache_clear()
    # Settings fields are class attrs evaluated at import — patch instances too.
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", secret, raising=False)
    monkeypatch.setattr(get_bot_settings(), "telegram_webhook_secret", secret, raising=False)
    monkeypatch.setattr(get_bot_settings(), "telegram_bot_token", "123456:TESTTOKEN", raising=False)
    yield secret
    get_settings.cache_clear()
    get_bot_settings.cache_clear()


@pytest.fixture
def webhook_app(webhook_secret):
    from app.routers.telegram_webhook import router

    app = FastAPI()
    app.include_router(router)
    return app


def test_webhook_path_helper(webhook_secret):
    from bot.webhook_setup import webhook_path, webhook_url

    assert webhook_path() == f"/telegram/webhook/{webhook_secret}"
    assert webhook_url().endswith(f"/telegram/webhook/{webhook_secret}")


def test_webhook_rejects_bad_secret(webhook_app):
    client = TestClient(webhook_app)
    r = client.post("/telegram/webhook/wrong-secret", json={"update_id": 1})
    assert r.status_code == 403


def test_webhook_ok_minimal_update(webhook_app, webhook_secret):
    fake_bot = MagicMock()
    fake_dp = MagicMock()
    fake_dp.feed_update = AsyncMock()

    with (
        patch("bot.aiogram_app.get_bot", return_value=fake_bot),
        patch("bot.aiogram_app.get_dispatcher", return_value=fake_dp),
    ):
        client = TestClient(webhook_app)
        r = client.post(f"/telegram/webhook/{webhook_secret}", json={"update_id": 99})

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    fake_dp.feed_update.assert_awaited()


def test_setup_routers_includes_commands():
    from bot.handlers import setup_routers

    root = setup_routers()
    assert root is not None
    assert len(root.sub_routers) >= 2
