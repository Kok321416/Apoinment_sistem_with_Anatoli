"""Dry-run gate before non-test Telegram broadcasts."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import Request

from app.config import get_settings
from app.services.broadcast import AUDIENCE_TEST_SELF

DRY_RUN_TTL_MINUTES = 30
SESSION_KEY = "broadcast_dry_runs"


def broadcast_require_dry_run() -> bool:
    settings = get_settings()
    raw = (__import__("os").getenv("BROADCAST_REQUIRE_DRY_RUN", "") or "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    return not settings.debug


def record_dry_run(request: Request, audience: str, count: int) -> None:
    if "session" not in request.scope:
        return
    runs: dict[str, Any] = dict(request.session.get(SESSION_KEY) or {})
    runs[audience] = {"count": int(count), "at": datetime.utcnow().isoformat()}
    request.session[SESSION_KEY] = runs


def dry_run_allows_enqueue(request: Request, audience: str, current_count: int) -> tuple[bool, str | None]:
    audience = (audience or "").strip().lower()
    if audience == AUDIENCE_TEST_SELF:
        return True, None
    if not broadcast_require_dry_run():
        return True, None
    if "session" not in request.scope:
        return False, "Сначала выполните Dry-run для выбранной аудитории."
    row = (request.session.get(SESSION_KEY) or {}).get(audience)
    if not row:
        return False, "Перед рассылкой обязателен Dry-run для этой аудитории (кнопка Dry-run)."
    try:
        at = datetime.fromisoformat(row.get("at") or "")
    except (TypeError, ValueError):
        return False, "Dry-run устарел. Повторите Dry-run."
    if datetime.utcnow() - at > timedelta(minutes=DRY_RUN_TTL_MINUTES):
        return False, f"Dry-run старше {DRY_RUN_TTL_MINUTES} мин. Повторите Dry-run."
    saved_count = int(row.get("count") or -1)
    if saved_count != int(current_count):
        return (
            False,
            f"Число получателей изменилось ({saved_count} → {current_count}). Повторите Dry-run.",
        )
    return True, None
