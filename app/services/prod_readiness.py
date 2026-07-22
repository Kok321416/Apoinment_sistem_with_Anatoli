"""Production readiness checks for dual-role + admin platform."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db_schema import get_schema_health
from app.services.dual_role_inventory import collect_dual_role_inventory

CheckLevel = Literal["ok", "warn", "fail"]


@dataclass
class ReadinessCheck:
    id: str
    level: CheckLevel
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "level": self.level, "message": self.message}


def _add(checks: list[ReadinessCheck], check_id: str, level: CheckLevel, message: str) -> None:
    checks.append(ReadinessCheck(id=check_id, level=level, message=message))


def run_prod_readiness(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    checks: list[ReadinessCheck] = []
    schema = get_schema_health()
    inventory = collect_dual_role_inventory(db)

    if schema.get("degraded"):
        _add(checks, "schema", "fail", f"Schema degraded: {schema.get('issues')}")
    elif schema.get("ready"):
        _add(checks, "schema", "ok", "Schema patches applied")
    else:
        _add(checks, "schema", "warn", "Schema health unknown (patches may not have run)")

    if s.secret_key in ("", "change-me-in-production"):
        level: CheckLevel = "fail" if not s.debug else "warn"
        _add(checks, "secret_key", level, "SECRET_KEY is default or empty")
    else:
        _add(checks, "secret_key", "ok", "SECRET_KEY is set")

    if not s.telegram_bot_token:
        _add(checks, "telegram_bot", "fail", "TELEGRAM_BOT_TOKEN is missing")
    else:
        _add(checks, "telegram_bot", "ok", "Telegram bot token configured")

    if not s.bot_api_secret:
        _add(checks, "bot_api_secret", "warn", "BOT_API_SECRET not set (bot API less secure)")
    else:
        _add(checks, "bot_api_secret", "ok", "BOT_API_SECRET configured")

    if not s.notify_dedup:
        _add(checks, "notify_dedup", "warn", "NOTIFY_DEDUP=false - dual users may get duplicate TG messages")
    else:
        _add(checks, "notify_dedup", "ok", "NOTIFY_DEDUP enabled")

    if not (s.smtp_host and s.smtp_user and s.smtp_password):
        _add(checks, "smtp", "warn", "SMTP not fully configured (email verification may fail)")
    else:
        _add(checks, "smtp", "ok", "SMTP configured")

    if s.site_url.startswith("http://") and not s.debug:
        _add(checks, "site_https", "warn", "SITE_URL is http - use HTTPS in production")
    else:
        _add(checks, "site_https", "ok", f"SITE_URL: {s.site_url}")

    if inventory.get("shared_integration_chats_count"):
        _add(
            checks,
            "shared_integration_chats",
            "fail",
            f"Shared Integration.telegram_chat_id: {inventory['shared_integration_chats_count']}",
        )
    else:
        _add(checks, "shared_integration_chats", "ok", "No shared specialist Telegram chats")

    if inventory.get("duplicate_telegram_social_uids_count"):
        _add(
            checks,
            "duplicate_social_uids",
            "fail",
            f"Duplicate telegram SocialAccount uids: {inventory['duplicate_telegram_social_uids_count']}",
        )
    else:
        _add(checks, "duplicate_social_uids", "ok", "No duplicate telegram SocialAccount uids")

    if not inventory.get("schema_has_client_user_id"):
        _add(checks, "client_user_id_column", "fail", "bookings.client_user_id column missing")
    else:
        _add(checks, "client_user_id_column", "ok", "client_user_id column present")

    if s.platform_admin_enabled:
        _add(checks, "platform_admin", "ok", "PLATFORM_ADMIN_ENABLED=true")
    else:
        _add(checks, "platform_admin", "warn", "PLATFORM_ADMIN_ENABLED=false - admin UI hidden")

    fail_count = sum(1 for c in checks if c.level == "fail")
    warn_count = sum(1 for c in checks if c.level == "warn")
    ok_count = sum(1 for c in checks if c.level == "ok")

    return {
        "ok": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "ok_count": ok_count,
        "checks": [c.as_dict() for c in checks],
        "inventory": inventory,
    }


def format_readiness_report(data: dict[str, Any]) -> str:
    lines = [
        "=== Production readiness ===",
        f"Status: {'PASS' if data['ok'] else 'FAIL'} "
        f"(ok={data['ok_count']}, warn={data['warn_count']}, fail={data['fail_count']})",
        "",
    ]
    for check in data["checks"]:
        lines.append(f"[{check['level'].upper():4}] {check['id']}: {check['message']}")
    lines.append("=== end ===")
    return "\n".join(lines)
