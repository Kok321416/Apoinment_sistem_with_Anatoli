"""Password reset tokens and admin-triggered reset emails."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PasswordResetToken, User

settings = get_settings()
RESET_HOURS = 24


def _expire_at() -> datetime:
    return datetime.utcnow() + timedelta(hours=RESET_HOURS)


def create_password_reset_token(db: Session, user: User) -> PasswordResetToken:
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used.is_(False),
    ).update({"used": True})
    row = PasswordResetToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32)[:64],
        expires_at=_expire_at(),
        used=False,
    )
    db.add(row)
    db.flush()
    return row


def get_valid_reset_token(db: Session, token: str) -> PasswordResetToken | None:
    token = (token or "").strip()
    if not token:
        return None
    row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == token, PasswordResetToken.used.is_(False))
        .first()
    )
    if not row:
        return None
    if row.expires_at < datetime.utcnow():
        return None
    return row


def consume_reset_token(db: Session, row: PasswordResetToken) -> None:
    row.used = True


def send_password_reset_email(db: Session, user: User) -> tuple[bool, str]:
    email = (user.email or user.username or "").strip()
    if not email or "@" not in email:
        return False, "У пользователя нет email для сброса."
    row = create_password_reset_token(db, user)
    link = f"{settings.site_url.rstrip('/')}/accounts/password/reset/?token={row.token}"
    from app.services.email import send_password_reset_link_email

    ok = send_password_reset_link_email(email, link)
    if ok:
        db.commit()
        return True, f"Письмо отправлено на {email}"
    db.rollback()
    return False, "Не удалось отправить письмо (SMTP)."
