"""Run Telegram bot: webhook is handled by FastAPI when TELEGRAM_WEBHOOK_SECRET is set.

Dev / fallback long polling:
  python -m bot.run
"""
from __future__ import annotations

import asyncio
import logging
import sys

from bot.aiogram_app import get_bot, get_dispatcher, setup_bot_meta, verify_bot_identity
from bot.config import get_bot_settings
from bot.webhook_setup import remove_webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def _run_polling() -> None:
    settings = get_bot_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    if settings.telegram_webhook_secret:
        logger.warning(
            "TELEGRAM_WEBHOOK_SECRET is set. Prefer FastAPI webhook and stop this process on prod. "
            "Continuing with polling after deleteWebhook."
        )
    bot = get_bot()
    dp = get_dispatcher()
    await verify_bot_identity(bot)
    await remove_webhook(bot)
    await setup_bot_meta(bot)
    logger.info("aiogram polling started. SITE_URL=%s", settings.site_url)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


def main() -> None:
    asyncio.run(_run_polling())


if __name__ == "__main__":
    main()
