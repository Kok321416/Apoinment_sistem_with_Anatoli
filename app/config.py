import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_site = (os.getenv("SITE_URL", "") or "").strip().rstrip("/") or "http://127.0.0.1:8000"
if _site and not _site.startswith("http"):
    _site = "https://" + _site


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    base_dir: Path = BASE_DIR
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    debug: bool = os.getenv("DEBUG", "True") == "True"
    allowed_hosts: list[str] = [
        h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
    ]
    site_url: str = _site
    timezone: str = os.getenv("TIMEZONE", "Europe/Moscow")

    db_name: str | None = os.getenv("DB_NAME")
    db_user: str = os.getenv("DB_USER", "appointment_user")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_host: str = (os.getenv("DB_HOST", "") or "").strip() or "localhost"
    db_port: str = os.getenv("DB_PORT", "3306")
    db_connect_timeout: int = _env_int("DB_CONNECT_TIMEOUT", 10)

    google_oauth_client_id: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    google_oauth_client_secret: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    google_calendar_scopes: list[str] = ["https://www.googleapis.com/auth/calendar.events"]

    yandex_oauth_client_id: str = (os.getenv("YANDEX_OAUTH_CLIENT_ID", "") or "").strip()
    yandex_oauth_client_secret: str = (os.getenv("YANDEX_OAUTH_CLIENT_SECRET", "") or "").strip()

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME", "")
    # Separate secret for bot -> API calls (recommended; do not reuse TELEGRAM_BOT_TOKEN in new setups)
    bot_api_secret: str = (os.getenv("BOT_API_SECRET", "") or "").strip()
    admin_telegram_username: str = os.getenv("ADMIN_TELEGRAM_USERNAME", "andrievskypsy")
    # Dual-role Phase 3 scaffold: when true, skip duplicate TG sends to same chat_id
    notify_dedup: bool = (os.getenv("NOTIFY_DEDUP", "") or "").strip().lower() in ("1", "true", "yes")
    # Dual-role Phase 5 rollback: force Consultant on every signup (old behavior)
    force_consultant_on_signup: bool = (os.getenv("FORCE_CONSULTANT_ON_SIGNUP", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    # SMTP для писем подтверждения email
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = _env_int("SMTP_PORT", 465)
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "") or os.getenv("SMTP_USER", "")
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "Все клиенты здесь")
    site_brand_name: str = os.getenv("SITE_BRAND_NAME", "Все клиенты здесь")
    support_email: str = os.getenv("SUPPORT_EMAIL", "kok321416x@yandex.ru")
    yandex_metrika_id: str = (os.getenv("YANDEX_METRIKA_ID", "110889652") or "").strip()
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")
    email_verify_hours: int = _env_int("EMAIL_VERIFY_HOURS", 24)
    email_resend_minutes: int = _env_int("EMAIL_RESEND_MINUTES", 5)

    media_root: Path = BASE_DIR / "media"
    static_dir: Path = BASE_DIR / "app" / "static"
    templates_dir: Path = BASE_DIR / "app" / "templates"

    session_cookie: str = "session"
    session_max_age: int = 60 * 60 * 24 * 14
    # none = Telegram Mini App WebView can keep session (requires HTTPS / Secure cookie).
    # Override with SESSION_SAME_SITE=lax for local http:// testing.
    session_same_site: str = (
        os.getenv("SESSION_SAME_SITE")
        or ("none" if (os.getenv("SITE_URL") or "").strip().lower().startswith("https://") else "lax")
    ).strip().lower()

    @property
    def database_url(self) -> str:
        if self.db_name:
            return (
                f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
            )
        return f"sqlite:///{self.base_dir / 'data.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
