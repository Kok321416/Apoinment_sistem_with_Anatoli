"""Shared keyboards / URLs for aiogram handlers."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.config import get_bot_settings


def site_url() -> str:
    return get_bot_settings().site_url.rstrip("/")


def mini_app_url(path: str = "/tg/", *, mode: str | None = None) -> str:
    base = site_url()
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    if mode in ("client", "specialist"):
        sep = "&" if "?" in path else "?"
        url = f"{url}{sep}mode={mode}"
    return url


def web_app_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


def url_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def mode_picker_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Я клиент", callback_data="mode_client"),
                InlineKeyboardButton(text="💼 Я специалист", callback_data="mode_specialist"),
            ]
        ]
    )


def client_start_keyboard(*, dual: bool) -> InlineKeyboardMarkup:
    rows = [
        [web_app_button("Открыть Mini App", mini_app_url("/tg/", mode="client"))],
        [web_app_button("Записаться", mini_app_url("/tg/", mode="client"))],
    ]
    if dual:
        rows.append([InlineKeyboardButton(text="Сменить роль", callback_data="pick_mode")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def specialist_start_keyboard(*, dual: bool) -> InlineKeyboardMarkup:
    rows = [
        [web_app_button("Кабинет специалиста", mini_app_url("/tg/", mode="specialist"))],
    ]
    if dual:
        rows.append([InlineKeyboardButton(text="Сменить роль", callback_data="pick_mode")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def remove_reply_keyboard() -> dict:
    return {"remove_keyboard": True}
