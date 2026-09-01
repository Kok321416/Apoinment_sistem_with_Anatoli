"""Shared specialist booking cancel flow for sync (legacy) and async (aiogram) bots."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROMPT_CANCEL_REASON = (
    "✏️ <b>Отмена консультации</b>\n\n"
    "Напишите причину отмены одним сообщением - её получит клиент в Telegram или на почту."
)


async def prompt_cancel_reason_aiogram(callback_message, booking_id: int) -> None:
    from bot.pending_cancel import set_pending_cancel

    set_pending_cancel(
        callback_message.chat.id,
        booking_id,
        message_id=callback_message.message_id,
    )
    await callback_message.answer(PROMPT_CANCEL_REASON)


def prompt_cancel_reason_sync(chat_id, booking_id: int, *, message_id: int | None = None, send_message) -> None:
    from bot.pending_cancel import set_pending_cancel

    set_pending_cancel(chat_id, booking_id, message_id=message_id)
    send_message(chat_id, PROMPT_CANCEL_REASON)


async def submit_cancel_reason_aiogram(message, reason: str) -> bool:
    from bot.api_client_async import post_site_api
    from bot.pending_cancel import clear_pending_cancel, get_pending_cancel
    from app.services.telegram import edit_telegram_message_reply_markup, specialist_booking_keyboard_after_cancel

    chat_id = message.chat.id
    pending = get_pending_cancel(chat_id)
    if not pending:
        return False
    status, data = await post_site_api(
        "/api/telegram/specialist-booking-cancel",
        {
            "telegram_chat_id": str(chat_id),
            "booking_id": pending["booking_id"],
            "reason": reason,
        },
    )
    clear_pending_cancel(chat_id)
    if status == 200 and data and data.get("success"):
        msg = data.get("message") or "Запись отменена"
        await message.answer(f"✅ {msg}")
        msg_id = pending.get("message_id")
        if msg_id is not None:
            try:
                edit_telegram_message_reply_markup(
                    chat_id,
                    msg_id,
                    specialist_booking_keyboard_after_cancel(),
                )
            except Exception:
                logger.warning("cancel markup update failed", exc_info=True)
        return True
    err = (data or {}).get("error") or "Не удалось отменить запись"
    await message.answer(f"❌ {err}")
    return False


def submit_cancel_reason_sync(chat_id, reason: str, *, send_message, edit_markup) -> bool:
    from bot import bot as legacy_bot
    from bot.pending_cancel import clear_pending_cancel, get_pending_cancel
    from app.services.telegram import specialist_booking_keyboard_after_cancel

    pending = get_pending_cancel(chat_id)
    if not pending:
        return False
    status, data = legacy_bot.post_site_api(
        "/api/telegram/specialist-booking-cancel",
        {
            "telegram_chat_id": str(chat_id),
            "booking_id": pending["booking_id"],
            "reason": reason,
        },
        timeout=8,
    )
    clear_pending_cancel(chat_id)
    if status == 200 and data and data.get("success"):
        msg = data.get("message") or "Запись отменена"
        send_message(chat_id, f"✅ {msg}")
        msg_id = pending.get("message_id")
        if msg_id is not None:
            try:
                edit_markup(chat_id, msg_id, specialist_booking_keyboard_after_cancel())
            except Exception:
                logger.warning("cancel markup update failed", exc_info=True)
        return True
    err = (data or {}).get("error") or "Не удалось отменить запись"
    send_message(chat_id, f"❌ {err}")
    return False
