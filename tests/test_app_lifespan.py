"""Startup work must run through the lifespan handler.

Startup used to be wired with the deprecated @app.on_event("startup"); nothing asserted it stayed
wired, so a bad migration to lifespan would have silently skipped schema checks and webhook setup.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module


def test_lifespan_runs_startup_once(monkeypatch):
    calls = []

    async def fake_startup():
        calls.append(True)

    monkeypatch.setattr(main_module, "_startup", fake_startup)
    monkeypatch.setattr("app.services.reminder_tick.schedule_reminders_tick", lambda **_kwargs: True)

    with TestClient(main_module.app) as client:
        assert client.get("/health").status_code == 200

    assert calls == [True]


def test_startup_is_not_registered_as_deprecated_event():
    assert not main_module.app.router.on_startup, "use the lifespan handler, not on_event('startup')"
