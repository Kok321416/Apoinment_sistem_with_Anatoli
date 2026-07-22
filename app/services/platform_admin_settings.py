"""Read-only platform settings and integration status (Admin A4)."""
from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings


def mask_secret(value: str, *, head: int = 4, tail: int = 4) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= head + tail:
        return "***"
    return f"{value[:head]}...{value[-tail:]}"


def integration_status(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    smtp_ok = bool(s.smtp_host and s.smtp_user and s.smtp_password)
    tg_ok = bool(s.telegram_bot_token)
    google_ok = bool(s.google_oauth_client_id and s.google_oauth_client_secret)
    yandex_ok = bool(s.yandex_oauth_client_id and s.yandex_oauth_client_secret)
    bot_api_ok = bool(s.bot_api_secret)

    return {
        "smtp": {
            "configured": smtp_ok,
            "host": s.smtp_host or "-",
            "port": s.smtp_port,
            "user": s.smtp_user or "-",
            "from": s.smtp_from or "-",
            "use_ssl": s.smtp_use_ssl,
            "password": mask_secret(s.smtp_password),
        },
        "telegram": {
            "configured": tg_ok,
            "username": s.telegram_bot_username or "-",
            "token": mask_secret(s.telegram_bot_token),
            "bot_api_secret": mask_secret(s.bot_api_secret),
            "bot_api_configured": bot_api_ok,
        },
        "google_oauth": {
            "configured": google_ok,
            "client_id": mask_secret(s.google_oauth_client_id, head=8, tail=4) or "-",
            "client_secret": mask_secret(s.google_oauth_client_secret),
        },
        "yandex_oauth": {
            "configured": yandex_ok,
            "client_id": mask_secret(s.yandex_oauth_client_id, head=6, tail=4) or "-",
            "client_secret": mask_secret(s.yandex_oauth_client_secret),
        },
    }


def platform_flags(settings: Settings | None = None) -> list[dict[str, Any]]:
    s = settings or get_settings()
    return [
        {"key": "PLATFORM_ADMIN_ENABLED", "value": s.platform_admin_enabled, "secret": False},
        {"key": "NOTIFY_DEDUP", "value": s.notify_dedup, "secret": False},
        {"key": "FORCE_CONSULTANT_ON_SIGNUP", "value": s.force_consultant_on_signup, "secret": False},
        {"key": "DEBUG", "value": s.debug, "secret": False},
        {"key": "SESSION_SAME_SITE", "value": s.session_same_site, "secret": False},
        {"key": "SITE_URL", "value": s.site_url, "secret": False},
        {"key": "SECRET_KEY", "value": mask_secret(s.secret_key), "secret": True},
        {"key": "TELEGRAM_BOT_TOKEN", "value": mask_secret(s.telegram_bot_token), "secret": True},
        {"key": "BOT_API_SECRET", "value": mask_secret(s.bot_api_secret), "secret": True},
        {"key": "SMTP_PASSWORD", "value": mask_secret(s.smtp_password), "secret": True},
        {"key": "DB_PASSWORD", "value": mask_secret(s.db_password), "secret": True},
    ]
