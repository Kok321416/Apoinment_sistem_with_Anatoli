import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_site = (os.getenv("SITE_URL", "") or "").strip().rstrip("/") or "http://127.0.0.1:8000"
if _site and not _site.startswith("http"):
    _site = "https://" + _site


class BotSettings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME", "")
    bot_api_secret: str = os.getenv("BOT_API_SECRET", "")
    admin_telegram_username: str = os.getenv("ADMIN_TELEGRAM_USERNAME", "andrievskypsy")
    site_url: str = _site


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
