"""TOTP 2FA for platform admins (stdlib only)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AdminTwoFactor, User
from app.services.totp_crypto import generate_totp_secret, provisioning_uri, verify_totp

__all__ = [
    "generate_totp_secret",
    "verify_totp",
    "provisioning_uri",
    "get_admin_2fa",
    "admin_2fa_enabled",
    "needs_admin_2fa",
    "ensure_admin_2fa_setup",
    "enable_admin_2fa",
    "disable_admin_2fa",
    "verify_admin_2fa_login",
]


def get_admin_2fa(db: Session, user_id: int) -> AdminTwoFactor | None:
    return db.get(AdminTwoFactor, user_id)


def admin_2fa_enabled(db: Session, user_id: int) -> bool:
    row = get_admin_2fa(db, user_id)
    return bool(row and row.enabled and row.secret)


def needs_admin_2fa(db: Session, user: User) -> bool:
    if not (user.is_staff or user.is_superuser):
        return False
    return admin_2fa_enabled(db, user.id)


def ensure_admin_2fa_setup(db: Session, user: User) -> AdminTwoFactor:
    row = get_admin_2fa(db, user.id)
    if row:
        return row
    row = AdminTwoFactor(user_id=user.id, secret=generate_totp_secret(), enabled=False, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def enable_admin_2fa(db: Session, user: User, code: str) -> tuple[bool, str]:
    row = ensure_admin_2fa_setup(db, user)
    if not verify_totp(row.secret, code):
        return False, "Неверный код"
    row.enabled = True
    row.enabled_at = datetime.utcnow()
    db.commit()
    return True, "2FA включена"


def disable_admin_2fa(db: Session, user_id: int) -> None:
    row = get_admin_2fa(db, user_id)
    if row:
        db.delete(row)
        db.commit()


def verify_admin_2fa_login(db: Session, user_id: int, code: str) -> bool:
    row = get_admin_2fa(db, user_id)
    if not row or not row.enabled:
        return True
    return verify_totp(row.secret, code)
