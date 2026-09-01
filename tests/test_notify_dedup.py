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
    assert len(sent) == 1
    assert sent[0][0] == "200"
    assert "Ваша запись Подтверждена" in sent[0][1]
    assert "Ура!" in sent[0][1]


def test_notify_status_dedup_sends_celebration_same_chat(monkeypatch):
    sent = []

    monkeypatch.setattr(tg, "notify_dedup_enabled", lambda: True)
    monkeypatch.setattr(tg, "send_telegram_async", lambda chat, text, token=None: sent.append((str(chat), text)))

    booking = _booking(client_tg=100, specialist_chat="100")
    tg.notify_booking_status_changed(MagicMock(), booking, old_status="pending")
    assert len(sent) == 1
    assert sent[0][0] == "100"
    assert "Ваша запись Подтверждена" in sent[0][1]
    assert "К вам запись" not in sent[0][1]


def test_notify_status_cancelled_still_notifies_specialist(monkeypatch):
    sent = []

    monkeypatch.setattr(tg, "notify_dedup_enabled", lambda: False)
    monkeypatch.setattr(tg, "send_telegram_async", lambda chat, text, token=None: sent.append((str(chat), text)))

    booking = _booking(client_tg=200, specialist_chat="100")
    booking.status = "cancelled"
    tg.notify_booking_status_changed(MagicMock(), booking, old_status="pending")
    assert len(sent) == 2
    assert "Ваша запись: изменение статуса" in sent[0][1]
    assert "К вам запись: статус обновлён" in sent[1][1]


def test_notify_specialist_new_booking_includes_action_buttons(monkeypatch):
    captured = {}

    def fake_send(chat_id, text, token=None, reply_markup=None, **kwargs):
        captured["chat_id"] = chat_id
        captured["reply_markup"] = reply_markup
        return True

    monkeypatch.setattr(tg, "_send_telegram", fake_send)
    monkeypatch.setattr(tg.settings, "site_url", "https://example.com")

    booking = _booking(client_tg=200, specialist_chat="100")
    booking.id = 55
    assert tg.notify_specialist_new_booking(booking) is True
    kb = captured["reply_markup"]
    assert kb["inline_keyboard"][0][0]["text"] == "✅ Подтвердить"
    assert kb["inline_keyboard"][0][0]["callback_data"] == "spec_book_confirm_55"
    assert kb["inline_keyboard"][1][0]["text"] == "📅 Перенести"
    assert kb["inline_keyboard"][1][0]["url"] == "https://example.com/booking/?reschedule=55"


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
    assert "Вы записались" in tg.format_client_booked_message(booking)
    assert "К вам новая запись" in tg.format_new_booking_message_for_specialist(booking)
    confirmed = tg.format_booking_status_changed_client(booking, "confirmed", "pending")
    assert "Ваша запись Подтверждена" in confirmed
    assert "Ура! Вася" in confirmed
    assert "одобрил время" in confirmed
    assert "Статус:" not in confirmed
    assert "Ваша запись: напоминание" in tg.format_reminder_message(booking, 6)
    assert "К вам запись: напоминание" in tg.format_specialist_reminder_message(booking, 6)
