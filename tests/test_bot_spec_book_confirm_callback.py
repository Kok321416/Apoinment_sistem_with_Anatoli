"""Sync bot handler: specialist booking confirm callback updates inline keyboard."""
from __future__ import annotations

from bot import bot


def test_handle_specialist_booking_confirm_updates_markup(monkeypatch):
    calls = {"answer": [], "edit": []}

    monkeypatch.setattr(
        bot,
        "post_site_api",
        lambda path, data, timeout=8: (
            200,
            {"success": True, "message": "Запись подтверждена", "booking_id": 5},
        ),
    )
    monkeypatch.setattr(
        bot,
        "answer_callback_query",
        lambda cqid, text=None, **kw: calls["answer"].append((cqid, text)) or True,
    )
    monkeypatch.setattr(
        bot,
        "edit_message_reply_markup",
        lambda chat_id, msg_id, markup: calls["edit"].append((chat_id, msg_id, markup)) or True,
    )
    monkeypatch.setattr(bot.settings, "site_url", "https://example.com")

    bot.handle_specialist_booking_confirm_callback("900111", "cq1", "5", 42)

    assert calls["answer"] == [("cq1", "✅ Запись подтверждена")]
    assert len(calls["edit"]) == 1
    chat_id, msg_id, markup = calls["edit"][0]
    assert chat_id == "900111"
    assert msg_id == 42
    assert markup["inline_keyboard"][0][0]["text"] == "📅 Перенести"
    assert markup["inline_keyboard"][1][0]["callback_data"] == "spec_book_cancel_5"


def test_handle_specialist_booking_confirm_repeat_still_updates_markup(monkeypatch):
    calls = {"edit": []}

    monkeypatch.setattr(
        bot,
        "post_site_api",
        lambda path, data, timeout=8: (
            200,
            {"success": True, "message": "Запись уже подтверждена", "already": True, "booking_id": 5},
        ),
    )
    monkeypatch.setattr(bot, "answer_callback_query", lambda *a, **k: True)
    monkeypatch.setattr(
        bot,
        "edit_message_reply_markup",
        lambda chat_id, msg_id, markup: calls["edit"].append(markup) or True,
    )
    monkeypatch.setattr(bot.settings, "site_url", "https://example.com")

    bot.handle_specialist_booking_confirm_callback("900111", "cq1", "5", 42)

    assert len(calls["edit"]) == 1
    assert calls["edit"][0]["inline_keyboard"][1][0]["callback_data"] == "spec_book_cancel_5"


def test_handle_specialist_booking_confirm_unauthorized_alert(monkeypatch):
    monkeypatch.setattr(
        bot,
        "post_site_api",
        lambda path, data, timeout=8: (200, {"success": False, "error": "specialist not connected"}),
    )
    alerts = []
    monkeypatch.setattr(
        bot,
        "answer_callback_query",
        lambda cqid, text=None, show_alert=False: alerts.append((text, show_alert)) or True,
    )
    monkeypatch.setattr(bot, "edit_message_reply_markup", lambda *a, **k: True)

    bot.handle_specialist_booking_confirm_callback("999", "cq1", "5", 42)

    assert alerts == [("❌ specialist not connected", True)]
