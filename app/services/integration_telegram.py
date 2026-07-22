"""Helpers for specialist Telegram Integration linking (Phase 4)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Integration


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


def claim_integration_telegram_chat(
    db: Session,
    integration: Integration,
    chat_id: str,
    *,
    bot_token: str | None = None,
    enable: bool = True,
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
    integration.telegram_chat_id = key
    if bot_token is not None:
        token = (bot_token or "").strip()
        integration.telegram_bot_token = token or None
    integration.telegram_connected = True
    if enable:
        integration.telegram_enabled = True
    return True, "OK"
