import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailAddress, EmailVerificationToken, User
from app.services.email import send_verification_email

settings = get_settings()


def _expire_at() -> datetime:
    return datetime.utcnow() + timedelta(hours=settings.email_verify_hours)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_verification_token(db: Session, user: User) -> EmailVerificationToken:
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used.is_(False),
    ).update({"used": True})
    token = EmailVerificationToken(
        user_id=user.id,
        token=_generate_code(),
        expires_at=_expire_at(),
        used=False,
    )
    db.add(token)
    db.flush()
    return token


def ensure_email_address(db: Session, user: User, email: str, verified: bool = False) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    row = db.query(EmailAddress).filter(EmailAddress.user_id == user.id, EmailAddress.email == email).first()
    if row:
        if verified:
            row.verified = True
            row.primary = True
            db.query(EmailAddress).filter(
                EmailAddress.user_id == user.id,
                EmailAddress.id != row.id,
            ).update({"primary": False})
        return
    if verified:
        db.query(EmailAddress).filter(EmailAddress.user_id == user.id).update({"primary": False})
    db.add(EmailAddress(email=email, verified=verified, primary=True, user_id=user.id))


def send_user_verification_email(db: Session, user: User) -> bool:
    token_row = create_verification_token(db, user)
    ok = send_verification_email(user.email, token_row.token)
    if ok:
        db.commit()
    return ok


def verify_email_code(db: Session, email: str, code: str) -> tuple[User | None, str | None]:
    email = (email or "").strip().lower()
    code = (code or "").strip().replace(" ", "")
    if not email or not code:
        return None, "Укажите почту и 6-значный код из письма."
    if not code.isdigit() or len(code) != 6:
        return None, "Код должен состоять из 6 цифр."
    user = db.query(User).filter(User.username == email).first()
    if not user:
        return None, "Пользователь с такой почтой не найден."
    if user.is_active:
        return user, None
    row = (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token == code,
            EmailVerificationToken.used.is_(False),
        )
        .order_by(EmailVerificationToken.created_at.desc())
        .first()
    )
    if not row:
        return None, "Неверный код. Проверьте письмо или запросите новый код."
    if row.expires_at < datetime.utcnow():
        return None, "Код истёк. Запросите новое письмо."
    user.is_active = True
    row.used = True
    ensure_email_address(db, user, user.email, verified=True)
    db.commit()
    return user, None


def verify_email_token(db: Session, token: str) -> tuple[User | None, str | None]:
    """Legacy link support: long tokens still work if present."""
    token = (token or "").strip()
    if token.isdigit() and len(token) == 6:
        return None, "Введите код на странице подтверждения почты."
    row = db.query(EmailVerificationToken).filter(EmailVerificationToken.token == token).first()
    if not row or row.used:
        return None, "Ссылка недействительна или уже использована."
    if row.expires_at < datetime.utcnow():
        return None, "Ссылка истекла. Запросите новый код на странице входа."
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
        return False, "Укажите почту."
    user = db.query(User).filter(User.username == email).first()
    if not user:
        return False, "Пользователь с такой почтой не найден."
    if user.is_active:
        return False, "Почта уже подтверждена. Можно войти."
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
    return True, "Письмо с кодом отправлено. Проверьте почту (и папку «Спам»)."
