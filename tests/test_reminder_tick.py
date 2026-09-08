"""Reminder scheduler tick (keepalive /health path)."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_health_schedules_reminder_tick_without_blocking():
    from app.main import app
    from app.services import reminder_tick

    called = []

    def _fake_schedule(**kwargs):
        called.append(True)
        return True

    with patch.object(reminder_tick, "schedule_reminders_tick", side_effect=_fake_schedule):
        # Patch where main imports inside health handler
        with patch("app.services.reminder_tick.schedule_reminders_tick", side_effect=_fake_schedule):
            client = TestClient(app)
            r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "schema" not in r.json()
    assert called


def test_schedule_reminders_tick_throttles():
    from app.services import reminder_tick

    reminder_tick._last_started = 0.0
    reminder_tick._running = False

    started = []

    def _fake_run():
        started.append(1)
        with reminder_tick._lock:
            reminder_tick._running = False

    with patch.object(reminder_tick, "_run_tick", side_effect=_fake_run):
        assert reminder_tick.schedule_reminders_tick(force=True) is True
        # Immediate second call must be throttled / already running or interval
        reminder_tick._running = False
        assert reminder_tick.schedule_reminders_tick(force=False) is False


def test_cron_reminders_accepts_telegram_bot_token_fallback(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "cron_secret", "")
    monkeypatch.setattr(settings, "bot_api_secret", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "test-bot-token-xyz")

    with patch("app.services.telegram.send_reminders_async", return_value={"client_1": 1}):
        client = TestClient(app)
        denied = client.post("/internal/cron/reminders/")
        assert denied.status_code == 403
        ok = client.post(
            "/internal/cron/reminders/",
            headers={"X-Cron-Secret": "test-bot-token-xyz"},
        )
        assert ok.status_code == 200
        assert ok.json()["ok"] is True
        assert ok.json()["sent"]["client_1"] == 1
