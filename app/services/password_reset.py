"""Password reset tokens and channel delivery (email admin, Telegram, Yandex)."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PasswordResetToken, SocialAccount, User

settings = get_settings()
logger = logging.getLogger(__name__)
RESET_HOURS = 24
GENERIC_OK = (
    "Если аккаунт найден и выбранный канал доступен, мы отправили ссылку для сброса пароля."
)
YANDEX_EMAIL_SUFFIXES = ("@yandex.ru", "@ya.ru", "@yandex.com", "@yandex.by", "@yandex.kz")


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


async def get_valid_reset_token_async(db, token: str) -> PasswordResetToken | None:
    token = (token or "").strip()
    if not token:
        return None
    row = (
        await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token == token,
                PasswordResetToken.used.is_(False),
            )
        )
    ).scalar_one_or_none()
    if not row:
        return None
    if row.expires_at < datetime.utcnow():
        return None
    return row


async def consume_reset_token_async(db, row: PasswordResetToken) -> None:
    row.used = True


def reset_link_for_token(token: str) -> str:
    return f"{settings.site_url.rstrip('/')}/accounts/password/reset/?token={token}"


def find_user_for_password_reset(db: Session, login_raw: str | None) -> User | None:
    from app.services.client_auth import login_identifier_to_username

    key = login_identifier_to_username(login_raw)
    if not key:
        return None
    user = db.query(User).filter(User.username == key).first()
    if user:
        return user
    if "@" in key:
        return db.query(User).filter(User.email == key).first()
    return None


async def find_user_for_password_reset_async(db, login_raw: str | None) -> User | None:
    from app.services.client_auth import login_identifier_to_username

    key = login_identifier_to_username(login_raw)
    if not key:
        return None
    user = (await db.execute(select(User).where(User.username == key))).scalar_one_or_none()
    if user:
        return user
    if "@" in key:
        return (await db.execute(select(User).where(User.email == key))).scalar_one_or_none()
    return None


def _telegram_chat_id_for_user(db: Session, user: User) -> str | None:
    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user.id, SocialAccount.provider == "telegram")
        .first()
    )
    if not sa or not sa.uid:
        return None
    uid = str(sa.uid).strip()
    return uid if uid.isdigit() else None


def _yandex_email_for_user(db: Session, user: User) -> str | None:
    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user.id, SocialAccount.provider == "yandex")
        .first()
    )
    if sa and sa.extra_data:
        try:
            extra = json.loads(sa.extra_data)
            email = (extra.get("default_email") or extra.get("email") or "").strip().lower()
            if email and "@" in email:
                return email
        except Exception:
            pass
    for candidate in ((user.email or "").strip().lower(), (user.username or "").strip().lower()):
        if candidate and any(candidate.endswith(suf) for suf in YANDEX_EMAIL_SUFFIXES):
            return candidate
    return None


async def _telegram_chat_id_for_user_async(db, user: User) -> str | None:
    sa = (
        await db.execute(
            select(SocialAccount).where(
                SocialAccount.user_id == user.id,
                SocialAccount.provider == "telegram",
            )
        )
    ).scalar_one_or_none()
    if not sa or not sa.uid:
        return None
    uid = str(sa.uid).strip()
    return uid if uid.isdigit() else None


async def _yandex_email_for_user_async(db, user: User) -> str | None:
    sa = (
        await db.execute(
            select(SocialAccount).where(
                SocialAccount.user_id == user.id,
                SocialAccount.provider == "yandex",
            )
        )
    ).scalar_one_or_none()
    if sa and sa.extra_data:
        try:
            extra = json.loads(sa.extra_data)
            email = (extra.get("default_email") or extra.get("email") or "").strip().lower()
            if email and "@" in email:
                return email
        except Exception:
            pass
    for candidate in ((user.email or "").strip().lower(), (user.username or "").strip().lower()):
        if candidate and any(candidate.endswith(suf) for suf in YANDEX_EMAIL_SUFFIXES):
            return candidate
    return None


def send_password_reset_email(db: Session, user: User) -> tuple[bool, str]:
    email = (user.email or user.username or "").strip()
    if not email or "@" not in email:
        return False, "У пользователя нет email для сброса."
    row = create_password_reset_token(db, user)
    link = reset_link_for_token(row.token)
    from app.services.email import send_password_reset_link_email

    ok = send_password_reset_link_email(email, link)
    if ok:
        db.commit()
        return True, f"Письмо отправлено на {email}"
    db.rollback()
    return False, "Не удалось отправить письмо (SMTP)."


def request_password_reset(
    db: Session,
    *,
    login_raw: str,
    channel: str,
) -> tuple[bool, str]:
    """Public forgot-password. Always returns generic success message to caller for UX."""
    channel = (channel or "").strip().lower()
    if channel not in ("telegram", "yandex"):
        return False, "Выберите канал: Телеграм или Яндекс."

    user = find_user_for_password_reset(db, login_raw)
    if not user or not user.is_active:
        return True, GENERIC_OK

    try:
        if channel == "telegram":
            chat_id = _telegram_chat_id_for_user(db, user)
            if not chat_id:
                logger.info("password_reset telegram skip user_id=%s no chat", user.id)
                return True, GENERIC_OK
            row = create_password_reset_token(db, user)
            link = reset_link_for_token(row.token)
            from app.services.telegram import send_telegram_message

            text = (
                "🔐 <b>Сброс пароля</b>\n\n"
                "Вы запросили восстановление доступа.\n"
                f'<a href="{link}">Открыть ссылку для нового пароля</a>\n\n'
                "Если это были не вы — просто игнорируйте сообщение."
            )
            ok = send_telegram_message(chat_id, text)
            if ok:
                db.commit()
            else:
                db.rollback()
            return True, GENERIC_OK

        # yandex
        email = _yandex_email_for_user(db, user)
        if not email:
            logger.info("password_reset yandex skip user_id=%s no email", user.id)
            return True, GENERIC_OK
        row = create_password_reset_token(db, user)
        link = reset_link_for_token(row.token)
        from app.services.email import send_password_reset_link_email

        ok = send_password_reset_link_email(email, link)
        if ok:
            db.commit()
        else:
            db.rollback()
        return True, GENERIC_OK
    except Exception:
        logger.exception("request_password_reset failed")
        try:
            db.rollback()
        except Exception:
            pass
        return True, GENERIC_OK


async def request_password_reset_async(
    db,
    *,
    login_raw: str,
    channel: str,
) -> tuple[bool, str]:
    """Async wrapper: resolve user on async session, deliver via sync SessionLocal helpers."""
    channel = (channel or "").strip().lower()
    if channel not in ("telegram", "yandex"):
        return False, "Выберите канал: Телеграм или Яндекс."

    user = await find_user_for_password_reset_async(db, login_raw)
    if not user or not user.is_active:
        return True, GENERIC_OK

    from app.database import SessionLocal

    sdb = SessionLocal()
    try:
        u = sdb.get(User, user.id)
        if not u:
            return True, GENERIC_OK
        return request_password_reset(sdb, login_raw=login_raw, channel=channel)
    finally:
        sdb.close()
