"""Deploy checklist helpers for admin Ops UI."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.services.prod_readiness import run_prod_readiness


def deploy_checklist(db: Session, settings: Settings | None = None) -> list[dict[str, Any]]:
    s = settings or get_settings()
    readiness = run_prod_readiness(db, s)
    by_id = {c["id"]: c for c in readiness["checks"]}

    def auto(item_id: str, label: str, *, invert: bool = False) -> dict[str, Any]:
        row = by_id.get(item_id)
        if not row:
            return {"id": item_id, "label": label, "status": "manual", "hint": "проверьте вручную"}
        level = row["level"]
        if invert:
            level = "ok" if level == "fail" else "warn" if level == "warn" else "manual"
        status = "ok" if level == "ok" else "fail" if level == "fail" else "warn"
        return {"id": item_id, "label": label, "status": status, "hint": row["message"]}

    return [
        auto("notify_dedup", "NOTIFY_DEDUP включён на проде"),
        auto("telegram_bot", "TELEGRAM_BOT_TOKEN задан"),
        auto("platform_admin", "PLATFORM_ADMIN_ENABLED"),
        auto("secret_key", "SECRET_KEY не дефолтный"),
        auto("shared_integration_chats", "Нет shared Integration.chat_id"),
        auto("duplicate_social_uids", "Нет duplicate telegram SocialAccount"),
        auto("smtp", "SMTP для писем"),
        {
            "id": "test_self",
            "label": "test_self рассылка прошла",
            "status": "manual",
            "hint": "Admin → Telegram → test_self",
        },
        {
            "id": "dry_run",
            "label": "Dry-run перед боевой рассылкой",
            "status": "manual",
            "hint": "Admin → Telegram → dry-run",
        },
        {
            "id": "e2e_dual",
            "label": "E2E dual-role (бот + сайт + Mini App)",
            "status": "manual",
            "hint": "DUAL_ROLE_MIGRATION_PLAN.md раздел 6",
        },
    ]
