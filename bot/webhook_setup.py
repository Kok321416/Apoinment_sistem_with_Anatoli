"""Webhook helpers for Telegram → FastAPI."""
from __future__ import annotations

import logging

from aiogram import Bot

from bot.config import get_bot_settings

logger = logging.getLogger(__name__)


def webhook_path() -> str | None:
    secret = get_bot_settings().telegram_webhook_secret
    if not secret:
        return None
    return f"/telegram/webhook/{secret}"


def webhook_url() -> str | None:
    path = webhook_path()
    if not path:
        return None
    return f"{get_bot_settings().site_url.rstrip('/')}{path}"


async def install_webhook(bot: Bot) -> bool:
    url = webhook_url()
    if not url:
        return False
    await bot.set_webhook(
        url=url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=False,
    )
    logger.info("Telegram webhook set: %s", url.split(get_bot_settings().telegram_webhook_secret)[0] + "***")
    return True


async def remove_webhook(bot: Bot) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("Telegram webhook deleted (polling mode)")
