"""Run Telegram bot: python -m bot.run"""
import logging
import sys

from bot.bot import run_long_polling
from bot.config import get_bot_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)


def main():
    settings = get_bot_settings()
    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)
    print(f"Starting bot. SITE_URL={settings.site_url}")
    run_long_polling()


if __name__ == "__main__":
    main()
