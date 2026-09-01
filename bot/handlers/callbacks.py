"""aiogram callback handlers (login / connect / booklink / mode)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client_async import post_site_api
from bot.copy import LOGIN_OPEN_SITE, MODE_PICK_TEXT, WELCOME_SPECIALIST_FIRST
from bot.handlers.commands import _fetch_capabilities, _set_ui_mode, apply_mode_ui
from bot.keyboards import mini_app_url, mode_picker_keyboard, web_app_button

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


async def prompt_login_confirm(message: Message, token: str) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить вход", callback_data=f"login_confirm_{token}")]
        ]
    )
    await message.answer(
        "🔐 <b>Вход на сайт</b>\n\nНажмите кнопку ниже, чтобы подтвердить вход через Телеграм.",
        reply_markup=kb,
    )


async def prompt_specialist_connect(message: Message, token: str) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить подключение", callback_data=f"spec_confirm_{token}")]
        ]
    )
    await message.answer(
        "👋 <b>Подключение Телеграм для уведомлений специалиста</b>",
        reply_markup=kb,
    )


async def prompt_booking_link(message: Message, token: str) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить и получать уведомления",
                    callback_data=f"booklink_{token}",
                )
            ]
        ]
    )
    await message.answer(
        "📌 <b>Подтвердите привязку Телеграм к вашей записи</b>",
        reply_markup=kb,
    )


@router.callback_query(F.data.in_({"mode_client", "mode_specialist"}))
async def on_mode_chosen(callback: CallbackQuery) -> None:
    await callback.answer()
    mode = "client" if callback.data == "mode_client" else "specialist"
    if not callback.message or not callback.from_user:
        return
    chat_id = callback.message.chat.id
    if not await _set_ui_mode(chat_id, mode):
        await callback.message.answer("Не удалось сохранить режим. Попробуйте /start ещё раз.")
        return
    caps = await _fetch_capabilities(chat_id, callback.from_user.id)
    # apply_mode_ui expects Message-like; reuse callback.message
    await apply_mode_ui(callback.message, mode, dual=bool(caps.get("dual")))


@router.callback_query(F.data == "pick_mode")
async def on_pick_mode(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message or not callback.from_user:
        return
    caps = await _fetch_capabilities(callback.message.chat.id, callback.from_user.id)
    if not caps.get("dual"):
        await callback.message.answer(
            "Сейчас доступен только один режим. Подключите уведомления специалиста в кабинете → Интеграции "
            "или запишитесь как клиент, чтобы появился второй режим."
        )
        return
    await callback.message.answer(MODE_PICK_TEXT, reply_markup=mode_picker_keyboard())


@router.callback_query(F.data.startswith("login_confirm_"))
async def on_login_confirm(callback: CallbackQuery) -> None:
    token = (callback.data or "").replace("login_confirm_", "", 1)
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    status, data = await post_site_api(
        "/api/telegram/confirm-login",
        {
            "token": token,
            "telegram_id": callback.from_user.id,
            "username": callback.from_user.username or "",
            "first_name": callback.from_user.first_name or "",
        },
    )
    if status == 200 and data and data.get("success"):
        await callback.answer()
        complete_url = data.get("complete_url", "")
        button_label = data.get("button_label") or LOGIN_OPEN_SITE
        hint = data.get("success_hint") or "Нажмите кнопку ниже, чтобы завершить вход в браузере."
        kb = None
        if complete_url:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=button_label[:64], url=complete_url)]
                ]
            )
        await callback.message.answer(f"✅ <b>Вход подтверждён.</b>\n\n{hint}", reply_markup=kb)
    else:
        msg = (data or {}).get("error", "Ссылка недействительна или истекла.")
        await callback.answer(msg[:200], show_alert=True)
        await callback.message.answer(f"❌ {msg}")


@router.callback_query(F.data.startswith("spec_confirm_"))
async def on_spec_confirm(callback: CallbackQuery) -> None:
    token = (callback.data or "").replace("spec_confirm_", "", 1)
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    status, data = await post_site_api(
        "/api/specialist/connect-telegram",
        {"link_token": token, "telegram_id": callback.from_user.id},
    )
    if status == 200 and data and data.get("success"):
        await callback.answer()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [web_app_button("Открыть кабинет", mini_app_url("/tg/", mode="specialist"))]
            ]
        )
        await callback.message.answer(WELCOME_SPECIALIST_FIRST, reply_markup=kb)
    else:
        msg = (data or {}).get("error", "Ссылка недействительна.")
        await callback.answer(msg[:200], show_alert=True)
        await callback.message.answer(f"❌ Не удалось подключить: {msg}")


@router.callback_query(F.data.startswith("booklink_"))
async def on_booklink(callback: CallbackQuery) -> None:
    token = (callback.data or "").replace("booklink_", "", 1)
    await callback.answer("Привязываем...")
    if not callback.from_user or not callback.message:
        return
    status, data = await post_site_api(
        "/api/booking/confirm-telegram",
        {"link_token": token, "telegram_id": callback.from_user.id},
    )
    if status == 200 and data and data.get("success"):
        await callback.message.answer("✅ Ваш Телеграм привязан к записи.")
    else:
        await callback.message.answer("❌ Ссылка недействительна или истекла.")


@router.callback_query(F.data.startswith("spec_book_confirm_"))
async def on_spec_book_confirm(callback: CallbackQuery) -> None:
    booking_id = (callback.data or "").replace("spec_book_confirm_", "", 1)
    if not callback.message:
        await callback.answer()
        return
    if not booking_id.isdigit():
        await callback.answer("Некорректный запрос", show_alert=True)
        return
    await callback.answer("Подтверждаем...")
    status, data = await post_site_api(
        "/api/telegram/specialist-booking-confirm",
        {
            "telegram_chat_id": callback.message.chat.id,
            "booking_id": booking_id,
        },
    )
    if status == 200 and data and data.get("success"):
        msg = data.get("message") or "Запись подтверждена"
        await callback.message.answer(f"✅ {msg}")
        return
    err = (data or {}).get("error") or "Не удалось подтвердить запись"
    await callback.message.answer(f"❌ {err}")


@router.callback_query(F.data.in_({"my_appointments", "history", "help", "spec_next", "apps_android_soon"}))
async def on_legacy_cb(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer("Эти кнопки больше не используются. Нажмите /start.")


@router.callback_query()
async def on_unknown_cb(callback: CallbackQuery) -> None:
    await callback.answer("Неизвестная кнопка", show_alert=True)
