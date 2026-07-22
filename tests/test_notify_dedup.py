"""Phase 3 notify dedup behavior (flag on)."""
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.telegram as tg


def _booking(*, client_tg, specialist_chat):
    integration = SimpleNamespace(
        telegram_connected=True,
        telegram_enabled=True,
        telegram_chat_id=specialist_chat,
        telegram_bot_token=None,
    )
    return SimpleNamespace(
        status="confirmed",
        telegram_id=client_tg,
        calendar=SimpleNamespace(
            name="Кабинет",
            consultant=SimpleNamespace(
                first_name="Иван",
                last_name="П",
                email="a@b.c",
                integration=integration,
            ),
        ),
        client_name="Клиент",
        client_phone="+1",
        client_telegram="",
        client_email="",
        service=SimpleNamespace(name="Услуга", duration_minutes=30),
        booking_date=date.today(),
        booking_time=time(12, 0),
        booking_end_time=None,
    )


def test_notify_status_sends_both_when_dedup_off(monkeypatch):
    sent = []

    monkeypatch.setattr(tg, "notify_dedup_enabled", lambda: False)
    monkeypatch.setattr(tg, "send_telegram_async", lambda chat, text, token=None: sent.append((str(chat), text, token)))

    booking = _booking(client_tg=200, specialist_chat="100")
    tg.notify_booking_status_changed(MagicMock(), booking, old_status="pending")
    assert len(sent) == 2
    assert sent[0][0] == "200"
    assert "Ваша запись" in sent[0][1]
    assert sent[1][0] == "100"
    assert "К вам запись" in sent[1][1]


def test_notify_status_dedup_skips_client_same_chat(monkeypatch):
    sent = []

    monkeypatch.setattr(tg, "notify_dedup_enabled", lambda: True)
    monkeypatch.setattr(tg, "send_telegram_async", lambda chat, text, token=None: sent.append((str(chat), text)))

    booking = _booking(client_tg=100, specialist_chat="100")
    tg.notify_booking_status_changed(MagicMock(), booking, old_status="pending")
    assert len(sent) == 1
    assert sent[0][0] == "100"
    assert "К вам запись" in sent[0][1]


def test_role_labels_in_templates():
    booking = SimpleNamespace(
        client_name="Вася",
        client_phone="+7",
        client_telegram="",
        client_email="",
        service=SimpleNamespace(name="Консультация", duration_minutes=60),
        booking_date=date.today(),
        booking_time=time(15, 0),
        booking_end_time=None,
        calendar=SimpleNamespace(
            name="Кабинет",
            consultant=SimpleNamespace(first_name="Иван", last_name="П", email="a@b.c"),
        ),
    )
    assert "Ваша запись" in tg.format_client_booked_message(booking)
    assert "К вам новая запись" in tg.format_new_booking_message_for_specialist(booking)
    assert "Ваша запись: напоминание" in tg.format_reminder_message(booking, 6)
    assert "К вам запись: напоминание" in tg.format_specialist_reminder_message(booking, 6)
