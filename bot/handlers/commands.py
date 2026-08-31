"""aiogram command handlers (/start, /help, /mode)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message, ReplyKeyboardRemove

from bot.api_client_async import post_site_api
from bot.copy import (
    HELP_TEXT,
    MODE_PICK_TEXT,
    SWITCH_ROLE_HINT,
    WELCOME_CLIENT,
    WELCOME_SPECIALIST,
)
from bot.keyboards import (
    client_start_keyboard,
    mini_app_url,
    mode_picker_keyboard,
    site_url,
    specialist_start_keyboard,
    url_button,
    web_app_button,
)
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)
router = Router(name="commands")

_LEGACY_REPLY_BUTTONS = frozenset({
    "📱 Записаться",
    "📋 Мои записи",
    "📝 Регистрация",
    "📜 История",
    "📞 Связаться",
    "❓ Помощь",
    "📅 Ближайшие записи",
    "📊 Статистика",
    "🔗 Управление аккаунтами",
    "🔄 Сменить роль",
    "📱 Приложение",
    "Приложение",
})


async def _fetch_capabilities(chat_id: int, user_id: int) -> dict:
    status, data = await post_site_api(
        "/api/telegram/capabilities",
        {"telegram_id": user_id, "telegram_chat_id": str(chat_id)},
    )
    if status == 200 and data and data.get("success") is True:
        return data
    return {
        "is_client": True,
        "is_specialist": False,
        "dual": False,
        "mode": "client",
        "needs_picker": False,
        "success": True,
    }


async def _set_ui_mode(chat_id: int, mode: str) -> bool:
    status, data = await post_site_api(
        "/api/telegram/ui-mode",
        {"telegram_chat_id": str(chat_id), "mode": mode},
    )
    return bool(status == 200 and data and data.get("success"))


async def apply_mode_ui(message: Message, mode: str, *, dual: bool) -> None:
    name = message.from_user.first_name if message.from_user else "друг"
    if mode == "specialist":
        text = WELCOME_SPECIALIST.format(name=name)
        if dual:
            text = f"{text}\n\n{SWITCH_ROLE_HINT}"
        await message.answer(text, reply_markup=specialist_start_keyboard(dual=dual))
    else:
        text = WELCOME_CLIENT.format(name=name)
        if dual:
            text = f"{text}\n\n{SWITCH_ROLE_HINT}"
        await message.answer(text, reply_markup=client_start_keyboard(dual=dual))


async def start_for_user(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    caps = await _fetch_capabilities(message.chat.id, user.id)
    dual = bool(caps.get("dual"))
    needs_picker = bool(caps.get("needs_picker"))
    mode = caps.get("mode")

    if needs_picker or (dual and not mode):
        await message.answer(MODE_PICK_TEXT, reply_markup=mode_picker_keyboard())
        return
    if dual and mode in ("client", "specialist"):
        await apply_mode_ui(message, mode, dual=True)
        return
    if caps.get("is_specialist") and not caps.get("is_client"):
        await apply_mode_ui(message, "specialist", dual=False)
        return
    await apply_mode_ui(message, "client", dual=False)


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject | None = None) -> None:
    arg = (command.args if command else "") or ""
    arg = arg.strip()
    user = message.from_user
    if user:
        try:
            from app.services.ops_alerts import maybe_bind_ops_alert_chat

            maybe_bind_ops_alert_chat(message.chat.id, user.username)
        except Exception:
            logger.warning("ops alert bind skipped", exc_info=True)

    if arg.startswith("link_"):
        token = arg.replace("link_", "", 1).strip()
        if token:
            from bot.handlers.callbacks import prompt_booking_link

            await prompt_booking_link(message, token)
            return
    if arg.startswith("login_"):
        token = arg.replace("login_", "", 1).strip()
        if token:
            from bot.handlers.callbacks import prompt_login_confirm

            await prompt_login_confirm(message, token)
            return
        await prompt_login_page(message)
        return
    if arg == "login" or arg.startswith("login"):
        await prompt_login_page(message)
        return
    if arg.startswith("connect_spec_"):
        token = arg.replace("connect_spec_", "", 1).strip()
        if token:
            from bot.handlers.callbacks import prompt_specialist_connect

            await prompt_specialist_connect(message, token)
            return
        await prompt_connect_page(message)
        return
    if arg == "connect" or arg.startswith("connect"):
        await prompt_connect_page(message)
        return
    if arg in ("open", "miniapp", "app", "tg"):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    web_app_button("Открыть Mini App", mini_app_url("/tg/")),
                    web_app_button("Записаться", mini_app_url("/book/")),
                ]
            ]
        )
        await message.answer("Откройте сервис внутри Telegram - так работает Mini App:", reply_markup=kb)
        return

    await start_for_user(message)


@router.message(Command("alerts"))
async def cmd_alerts(message: Message) -> None:
    user = message.from_user
    from app.services.ops_alerts import is_ops_alert_user, maybe_bind_ops_alert_chat, ops_alert_username

    if not user or not is_ops_alert_user(user.username):
        await message.answer("Эта команда только для оператора.")
        return
    maybe_bind_ops_alert_chat(message.chat.id, user.username)
    await message.answer(
        f"Алерты системных ошибок будут приходить сюда (@{ops_alert_username()})."
    )


async def prompt_login_page(message: Message) -> None:
    from bot.copy import LOGIN_OPEN_SITE  # noqa: F401 — label unused, keep site button

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[url_button("🔐 Войти на сайт", f"{site_url()}/login/")]]
    )
    await message.answer(
        "👋 <b>Вход на сайт через Телеграм</b>\n\n"
        "Откройте страницу входа на сайте и нажмите «Телеграм» - "
        "бот отправит ссылку для подтверждения.",
        reply_markup=kb,
    )


async def prompt_connect_page(message: Message) -> None:
    from bot.copy import CONNECT_SITE

    connect_url = f"{site_url()}/accounts/telegram/login/?process=connect&next=/profile/"
    kb = InlineKeyboardMarkup(inline_keyboard=[[url_button(CONNECT_SITE, connect_url)]])
    await message.answer("👋 <b>Подключение Телеграм к аккаунту</b>", reply_markup=kb)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [web_app_button("Открыть Mini App", mini_app_url("/tg/"))],
            [web_app_button("Записаться", mini_app_url("/book/"))],
        ]
    )
    await message.answer(HELP_TEXT.format(site_url=site_url()), reply_markup=kb)


@router.message(Command("mode"))
async def cmd_mode(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    caps = await _fetch_capabilities(message.chat.id, user.id)
    if not caps.get("dual"):
        await message.answer(
            "Сейчас доступен только один режим. Подключите уведомления специалиста в кабинете → Интеграции "
            "или запишитесь как клиент, чтобы появился второй режим."
        )
        return
    await message.answer(MODE_PICK_TEXT, reply_markup=mode_picker_keyboard())


@router.message(F.text.in_(_LEGACY_REPLY_BUTTONS))
async def legacy_reply(message: Message) -> None:
    if message.text == "🔄 Сменить роль":
        await cmd_mode(message)
        return
    await message.answer(
        "Старое меню чата отключено. Нажмите /start - инструкция и кнопка Mini App.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.text)
async def fallback_text(message: Message) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        return
    await message.answer(
        "Бот отвечает на /start, /help и /mode. Запись и кабинет - в Mini App "
        "(кнопка «Открыть» у поля ввода)."
    )
