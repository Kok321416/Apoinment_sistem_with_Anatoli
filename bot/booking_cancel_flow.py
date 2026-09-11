"""Shared specialist booking cancel flow for sync (legacy) and async (aiogram) bots."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROMPT_CANCEL_REASON = (
    "✏️ <b>Отмена консультации</b>\n\n"
    "Напишите причину отмены одним сообщением - её получит клиент в Telegram или на почту."
)

# Cancel commits on the site first, then notifies; bot must wait long enough and retry
# (idempotent: already-cancelled is still success) so a slow/proxy timeout is not shown as ❌.
_CANCEL_API_TIMEOUT = 20
_CANCEL_API_RETRIES = 2


def _cancel_succeeded(status: int, data: dict | None) -> bool:
    return bool(status == 200 and data and data.get("success"))


def _cancel_error_message(status: int, data: dict | None) -> str:
    if data and data.get("error"):
        return str(data["error"])
    if status in (0, None):
        return (
            "Не удалось подтвердить отмену в боте. "
            "Проверьте запись на сайте — она могла уже отмениться."
        )
    return "Не удалось отменить запись"


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


async def _post_cancel_aiogram(chat_id, booking_id: int, reason: str):
    from bot.api_client_async import post_site_api

    payload = {
        "telegram_chat_id": str(chat_id),
        "booking_id": booking_id,
        "reason": reason,
    }
    status, data = 0, None
    for attempt in range(_CANCEL_API_RETRIES):
        status, data = await post_site_api(
            "/api/telegram/specialist-booking-cancel",
            payload,
            timeout=_CANCEL_API_TIMEOUT,
        )
        if _cancel_succeeded(status, data):
            return status, data
        # Do not retry clear client/auth errors
        if status in (400, 403, 404) and data and data.get("error"):
            return status, data
        logger.warning(
            "cancel API attempt %s failed status=%s data=%s",
            attempt + 1,
            status,
            (data or {}) if data is not None else None,
        )
    return status, data


def _post_cancel_sync(chat_id, booking_id: int, reason: str):
    from bot import bot as legacy_bot

    payload = {
        "telegram_chat_id": str(chat_id),
        "booking_id": booking_id,
        "reason": reason,
    }
    status, data = 0, None
    for attempt in range(_CANCEL_API_RETRIES):
        status, data = legacy_bot.post_site_api(
            "/api/telegram/specialist-booking-cancel",
            payload,
            timeout=_CANCEL_API_TIMEOUT,
        )
        if _cancel_succeeded(status, data):
            return status, data
        if status in (400, 403, 404) and data and data.get("error"):
            return status, data
        logger.warning(
            "cancel API attempt %s failed status=%s data=%s",
            attempt + 1,
            status,
            (data or {}) if data is not None else None,
        )
    return status, data


async def submit_cancel_reason_aiogram(message, reason: str) -> bool:
    from bot.pending_cancel import clear_pending_cancel, get_pending_cancel
    from app.services.telegram import edit_telegram_message_reply_markup, specialist_booking_keyboard_after_cancel

    chat_id = message.chat.id
    pending = get_pending_cancel(chat_id)
    if not pending:
        return False
    status, data = await _post_cancel_aiogram(chat_id, pending["booking_id"], reason)
    clear_pending_cancel(chat_id)
    if _cancel_succeeded(status, data):
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
    err = _cancel_error_message(status, data)
    await message.answer(f"❌ {err}")
    return False


def submit_cancel_reason_sync(chat_id, reason: str, *, send_message, edit_markup) -> bool:
    from bot.pending_cancel import clear_pending_cancel, get_pending_cancel
    from app.services.telegram import specialist_booking_keyboard_after_cancel

    pending = get_pending_cancel(chat_id)
    if not pending:
        return False
    status, data = _post_cancel_sync(chat_id, pending["booking_id"], reason)
    clear_pending_cancel(chat_id)
    if _cancel_succeeded(status, data):
        msg = data.get("message") or "Запись отменена"
        send_message(chat_id, f"✅ {msg}")
        msg_id = pending.get("message_id")
        if msg_id is not None:
            try:
                edit_markup(chat_id, msg_id, specialist_booking_keyboard_after_cancel())
            except Exception:
                logger.warning("cancel markup update failed", exc_info=True)
        return True
    err = _cancel_error_message(status, data)
    send_message(chat_id, f"❌ {err}")
    return False
