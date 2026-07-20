import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_site = (os.getenv("SITE_URL", "") or "").strip().rstrip("/") or "http://127.0.0.1:8000"
if _site and not _site.startswith("http"):
    _site = "https://" + _site

_internal = (os.getenv("SITE_INTERNAL_URL", "") or "").strip().rstrip("/")
if not _internal:
    _internal = "http://127.0.0.1:8000"


class BotSettings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME", "")
    bot_api_secret: str = (os.getenv("BOT_API_SECRET", "") or "").strip()
    admin_telegram_username: str = os.getenv("ADMIN_TELEGRAM_USERNAME", "andrievskypsy")
    site_url: str = _site
    site_internal_url: str = _internal


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
