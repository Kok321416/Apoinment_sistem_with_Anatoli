"""Opt-in TOTP 2FA for specialists (users with a Consultant profile)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Consultant, User, UserTwoFactor
from app.services.totp_crypto import generate_totp_secret, provisioning_uri, verify_totp


def user_is_specialist(db: Session, user_id: int) -> bool:
    return db.query(Consultant.id).filter(Consultant.user_id == user_id).first() is not None


def get_user_2fa(db: Session, user_id: int) -> UserTwoFactor | None:
    return db.get(UserTwoFactor, user_id)


def specialist_2fa_enabled(db: Session, user_id: int) -> bool:
    row = get_user_2fa(db, user_id)
    return bool(row and row.enabled and row.secret)


def needs_specialist_2fa(db: Session, user: User) -> bool:
    try:
        if not user_is_specialist(db, user.id):
            return False
        return specialist_2fa_enabled(db, user.id)
    except Exception:
        # Missing table / schema drift must not break Mini App login.
        return False


def ensure_specialist_2fa_setup(db: Session, user: User) -> UserTwoFactor:
    row = get_user_2fa(db, user.id)
    if row:
        return row
    row = UserTwoFactor(user_id=user.id, secret=generate_totp_secret(), enabled=False, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def enable_specialist_2fa(db: Session, user: User, code: str) -> tuple[bool, str]:
    if not user_is_specialist(db, user.id):
        return False, "2FA доступна только специалистам"
    row = ensure_specialist_2fa_setup(db, user)
    if not verify_totp(row.secret, code):
        return False, "Неверный код"
    row.enabled = True
    row.enabled_at = datetime.utcnow()
    db.commit()
    return True, "Двухфакторная аутентификация включена"


def disable_specialist_2fa(db: Session, user: User, code: str) -> tuple[bool, str]:
    row = get_user_2fa(db, user.id)
    if not row or not row.enabled:
        return True, "2FA уже выключена"
    if not verify_totp(row.secret, code):
        return False, "Неверный код"
    db.delete(row)
    db.commit()
    return True, "Двухфакторная аутентификация отключена"


def verify_specialist_2fa_login(db: Session, user_id: int, code: str) -> bool:
    row = get_user_2fa(db, user_id)
    if not row or not row.enabled:
        return True
    return verify_totp(row.secret, code)


def specialist_2fa_provisioning(db: Session, user: User) -> tuple[str, str]:
    """Return (secret, otpauth_uri) for setup UI. Creates pending row if needed."""
    row = ensure_specialist_2fa_setup(db, user)
    email = (user.email or user.username or f"user{user.id}").strip()
    return row.secret, provisioning_uri(row.secret, email)
