"""aiogram Bot + Dispatcher (singleton for FastAPI webhook / polling)."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_bot_settings

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dp: Dispatcher | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        settings = get_bot_settings()
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
        _bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    return _bot


def _build_storage():
    settings = get_bot_settings()
    if settings.redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage

            return RedisStorage.from_url(settings.redis_url)
        except Exception as exc:
            logger.warning("Redis FSM unavailable (%s), using MemoryStorage", exc)
    return MemoryStorage()


def get_dispatcher() -> Dispatcher:
    global _dp
    if _dp is None:
        from bot.handlers import setup_routers

        _dp = Dispatcher(storage=_build_storage())
        _dp.include_router(setup_routers())
    return _dp


async def setup_bot_meta(bot: Bot) -> None:
    """Commands + Menu Button (same as legacy bot)."""
    from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

    from bot.copy import BOTFATHER
    from bot.keyboards import mini_app_url

    commands = [BotCommand(command=c, description=d[:256]) for c, d in BOTFATHER.get("commands") or []]
    if commands:
        await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=mini_app_url("/tg/")))
    )


async def verify_bot_identity(bot: Bot) -> None:
    settings = get_bot_settings()
    expected = settings.telegram_bot_username.lstrip("@").lower()
    me = await bot.get_me()
    actual = (me.username or "").lower()
    if actual:
        logger.info("Telegram bot identity: @%s", actual)
    if expected and actual and expected != actual:
        logger.error(
            "TELEGRAM_BOT_USERNAME=%s but token belongs to @%s",
            settings.telegram_bot_username,
            actual,
        )
