"""Outbox marks retry when specialist TG delivery fails."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.telegram import NotifyDeliveryError, on_booking_created


def test_on_booking_created_raises_when_specialist_send_fails(monkeypatch):
    booking = SimpleNamespace(
        id=7,
        telegram_id=None,
        calendar=SimpleNamespace(
            consultant=SimpleNamespace(
                integration=SimpleNamespace(
                    telegram_connected=True,
                    telegram_enabled=True,
                    telegram_chat_id="111",
                    telegram_bot_token=None,
                )
            )
        ),
    )
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.telegram.send_telegram_message",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "app.services.telegram._notify_client_fallback",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.google_calendar.sync_booking_to_google",
        lambda *a, **k: None,
    )

    with pytest.raises(NotifyDeliveryError):
        on_booking_created(db, booking)


def test_on_booking_created_skip_no_chat_does_not_raise(monkeypatch):
    booking = SimpleNamespace(
        id=8,
        telegram_id=None,
        calendar=SimpleNamespace(consultant=SimpleNamespace(integration=None)),
    )
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.telegram._notify_client_fallback",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.google_calendar.sync_booking_to_google",
        lambda *a, **k: None,
    )
    on_booking_created(db, booking)  # no raise
