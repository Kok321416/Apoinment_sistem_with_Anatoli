import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailAddress, EmailVerificationToken, User
from app.services.email import send_verification_email

settings = get_settings()


def _expire_at() -> datetime:
    return datetime.utcnow() + timedelta(hours=settings.email_verify_hours)


def create_verification_token(db: Session, user: User) -> EmailVerificationToken:
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used.is_(False),
    ).update({"used": True})
    token = EmailVerificationToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        expires_at=_expire_at(),
        used=False,
    )
    db.add(token)
    db.flush()
    return token


def ensure_email_address(db: Session, user: User, email: str, verified: bool = False) -> None:
    row = db.query(EmailAddress).filter(EmailAddress.user_id == user.id, EmailAddress.email == email).first()
    if row:
        if verified:
            row.verified = True
        return
    db.add(EmailAddress(email=email, verified=verified, primary=True, user_id=user.id))


def send_user_verification_email(db: Session, user: User) -> bool:
    token_row = create_verification_token(db, user)
    db.commit()
    confirm_url = f"{settings.site_url.rstrip('/')}/accounts/confirm-email/{token_row.token}/"
    return send_verification_email(user.email, confirm_url)


def verify_email_token(db: Session, token: str) -> tuple[User | None, str | None]:
    row = db.query(EmailVerificationToken).filter(EmailVerificationToken.token == token).first()
    if not row or row.used:
        return None, "Ссылка недействительна или уже использована."
    if row.expires_at < datetime.utcnow():
        return None, "Ссылка истекла. Запросите новое письмо на странице входа."
    user = db.get(User, row.user_id)
    if not user:
        return None, "Пользователь не найден."
    user.is_active = True
    row.used = True
    ensure_email_address(db, user, user.email, verified=True)
    db.commit()
    return user, None


def resend_verification_email(db: Session, email: str) -> tuple[bool, str]:
    email = (email or "").strip().lower()
    if not email:
        return False, "Укажите email."
    user = db.query(User).filter(User.username == email).first()
    if not user:
        return False, "Пользователь с таким email не найден."
    if user.is_active:
        return False, "Email уже подтверждён. Можно войти."
    last = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.user_id == user.id)
        .order_by(EmailVerificationToken.created_at.desc())
        .first()
    )
    if last and not last.used and (datetime.utcnow() - last.created_at).total_seconds() < settings.email_resend_minutes * 60:
        return False, f"Подождите {settings.email_resend_minutes} мин. перед повторной отправкой."
    if not send_user_verification_email(db, user):
        return False, "Не удалось отправить письмо. Проверьте настройки SMTP на сервере."
    return True, "Письмо отправлено. Проверьте почту (и папку «Спам»)."
