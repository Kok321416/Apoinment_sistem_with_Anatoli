"""Telegram bot capabilities and UI mode (Phase 7)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Booking, Consultant, SocialAccount, TelegramUiPreference
from app.services.integration_telegram import find_integration_by_chat_id, normalize_telegram_chat_id

MODE_CLIENT = "client"
MODE_SPECIALIST = "specialist"
VALID_MODES = frozenset({MODE_CLIENT, MODE_SPECIALIST})


def resolve_capabilities(db: Session, *, telegram_id: int | str | None, telegram_chat_id: str | None) -> dict:
    tid = None
    if telegram_id is not None:
        try:
            tid = int(telegram_id)
        except (TypeError, ValueError):
            tid = None
    chat_key = normalize_telegram_chat_id(telegram_chat_id) or (str(tid) if tid is not None else None)

    is_client = False
    if tid is not None:
        if db.query(Booking.id).filter(Booking.telegram_id == tid).first():
            is_client = True
        else:
            sa = (
                db.query(SocialAccount)
                .filter(SocialAccount.provider == "telegram", SocialAccount.uid == str(tid))
                .first()
            )
            if sa:
                is_client = True

    is_specialist = False
    if chat_key and find_integration_by_chat_id(db, chat_key):
        is_specialist = True
    elif tid is not None:
        sa = (
            db.query(SocialAccount)
            .filter(SocialAccount.provider == "telegram", SocialAccount.uid == str(tid))
            .first()
        )
        if sa and db.query(Consultant.id).filter(Consultant.user_id == sa.user_id).first():
            is_specialist = True

    # Everyone can act as client for booking UX even without history
    if not is_client and not is_specialist:
        is_client = True

    stored = None
    if chat_key:
        pref = db.get(TelegramUiPreference, chat_key)
        if pref and pref.mode in VALID_MODES:
            stored = pref.mode

    mode = stored
    if mode == MODE_SPECIALIST and not is_specialist:
        mode = MODE_CLIENT if is_client else None
    if mode == MODE_CLIENT and not is_client and is_specialist:
        mode = MODE_SPECIALIST
    if mode is None:
        if is_specialist and not is_client:
            mode = MODE_SPECIALIST
        elif is_client and not is_specialist:
            mode = MODE_CLIENT
        elif is_client and is_specialist:
            mode = stored  # may still be None → bot shows picker
        else:
            mode = MODE_CLIENT

    return {
        "success": True,
        "is_client": bool(is_client),
        "is_specialist": bool(is_specialist),
        "dual": bool(is_client and is_specialist),
        "mode": mode,
        "needs_picker": bool(is_client and is_specialist and stored is None),
    }


def get_ui_mode(db: Session, chat_id: str) -> str | None:
    key = normalize_telegram_chat_id(chat_id)
    if not key:
        return None
    pref = db.get(TelegramUiPreference, key)
    if pref and pref.mode in VALID_MODES:
        return pref.mode
    return None


def set_ui_mode(db: Session, chat_id: str, mode: str) -> tuple[bool, str]:
    key = normalize_telegram_chat_id(chat_id)
    if not key:
        return False, "chat_id required"
    mode = (mode or "").strip().lower()
    if mode not in VALID_MODES:
        return False, "mode must be client or specialist"
    pref = db.get(TelegramUiPreference, key)
    if not pref:
        pref = TelegramUiPreference(chat_id=key, mode=mode, updated_at=datetime.utcnow())
        db.add(pref)
    else:
        pref.mode = mode
        pref.updated_at = datetime.utcnow()
    db.commit()
    return True, "OK"
