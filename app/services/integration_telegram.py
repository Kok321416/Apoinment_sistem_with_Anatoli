"""Helpers for specialist Telegram Integration linking (Phase 4 + audit Phase 9)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Integration, IntegrationTelegramAudit


def normalize_telegram_chat_id(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return str(int(s))
    return s


def find_integration_by_chat_id(db: Session, chat_id: str, *, exclude_id: int | None = None) -> Integration | None:
    key = normalize_telegram_chat_id(chat_id)
    if not key:
        return None
    q = db.query(Integration).filter(Integration.telegram_chat_id.isnot(None))
    if exclude_id is not None:
        q = q.filter(Integration.id != exclude_id)
    for row in q.all():
        if normalize_telegram_chat_id(row.telegram_chat_id) == key:
            return row
    return None


def _log_chat_change(
    db: Session,
    integration: Integration,
    *,
    old_chat_id: str | None,
    new_chat_id: str | None,
    source: str,
    actor_user_id: int | None = None,
) -> None:
    old_n = normalize_telegram_chat_id(old_chat_id)
    new_n = normalize_telegram_chat_id(new_chat_id)
    if old_n == new_n:
        return
    db.add(
        IntegrationTelegramAudit(
            integration_id=integration.id,
            consultant_id=integration.consultant_id,
            old_chat_id=old_n,
            new_chat_id=new_n,
            source=(source or "unknown")[:64],
            actor_user_id=actor_user_id,
            created_at=datetime.utcnow(),
        )
    )


def claim_integration_telegram_chat(
    db: Session,
    integration: Integration,
    chat_id: str,
    *,
    bot_token: str | None = None,
    enable: bool = True,
    source: str = "claim",
    actor_user_id: int | None = None,
) -> tuple[bool, str]:
    """
    Bind chat_id to this Integration for specialist notifications.
    Fails if another consultant already owns the same chat.
    """
    key = normalize_telegram_chat_id(chat_id)
    if not key:
        return False, "Укажите идентификатор чата."
    conflict = find_integration_by_chat_id(db, key, exclude_id=integration.id)
    if conflict:
        return False, "Этот Telegram уже подключён к другому специалисту. Отключите его там или используйте другой чат."
    old = integration.telegram_chat_id
    integration.telegram_chat_id = key
    if bot_token is not None:
        token = (bot_token or "").strip()
        integration.telegram_bot_token = token or None
    integration.telegram_connected = True
    if enable:
        integration.telegram_enabled = True
    _log_chat_change(
        db,
        integration,
        old_chat_id=old,
        new_chat_id=key,
        source=source,
        actor_user_id=actor_user_id,
    )
    return True, "OK"


def clear_integration_telegram_chat(
    db: Session,
    integration: Integration,
    *,
    source: str = "disconnect",
    actor_user_id: int | None = None,
) -> None:
    old = integration.telegram_chat_id
    integration.telegram_connected = False
    integration.telegram_bot_token = None
    integration.telegram_chat_id = None
    integration.telegram_link_token = None
    integration.telegram_link_token_created_at = None
    _log_chat_change(
        db,
        integration,
        old_chat_id=old,
        new_chat_id=None,
        source=source,
        actor_user_id=actor_user_id,
    )
