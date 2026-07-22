"""Telegram bot login flow (without Login Widget)."""
import json
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.deps import normalize_phone
from app.models import Category, Consultant, Integration, SocialAccount, TelegramLoginRequest, User
from app.services.bookings import parse_fio

LOGIN_TTL_MINUTES = 15


def _safe_next_url(next_url: str | None) -> str:
    url = (next_url or "/").strip()
    if not url.startswith("/") or url.startswith("//"):
        return "/"
    return url


def create_login_request(
    db: Session,
    *,
    next_url: str = "/",
    process: str = "login",
    register_fio: str | None = None,
    register_phone: str | None = None,
    connect_user_id: int | None = None,
) -> TelegramLoginRequest:
    now = datetime.utcnow()
    req = TelegramLoginRequest(
        token=secrets.token_urlsafe(24),
        next_url=_safe_next_url(next_url),
        process=process,
        register_fio=(register_fio or "").strip() or None,
        register_phone=normalize_phone(register_phone) or None,
        connect_user_id=connect_user_id,
        created_at=now,
        expires_at=now + timedelta(minutes=LOGIN_TTL_MINUTES),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def get_active_login_request(db: Session, token: str) -> TelegramLoginRequest | None:
    req = db.query(TelegramLoginRequest).filter(TelegramLoginRequest.token == token).first()
    if not req or req.completed:
        return None
    if req.expires_at < datetime.utcnow():
        return None
    return req


def _ensure_social_account(
    db: Session,
    *,
    user_id: int,
    telegram_id: str,
    username: str,
    first_name: str,
) -> None:
    existing = db.query(SocialAccount).filter(
        SocialAccount.provider == "telegram",
        SocialAccount.uid == telegram_id,
    ).first()
    if existing:
        return
    db.add(
        SocialAccount(
            provider="telegram",
            uid=telegram_id,
            user_id=user_id,
            extra_data=json.dumps({"username": username, "first_name": first_name}),
        )
    )


def _maybe_update_consultant_nickname(db: Session, user: User, username: str) -> None:
    if not username:
        return
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
    if consultant and not (consultant.telegram_nickname or "").strip():
        consultant.telegram_nickname = username


def _find_or_create_user_for_telegram(
    db: Session,
    telegram_id: str,
    username: str,
    first_name: str,
    register_fio: str | None,
    register_phone: str | None,
) -> User:
    """
    Login/signup via Telegram.

    Phase 4: does NOT write Integration.telegram_chat_id.
    Specialist notifications are linked only via Integrations UI / connect_spec_*.
    """
    social = db.query(SocialAccount).filter(
        SocialAccount.provider == "telegram",
        SocialAccount.uid == telegram_id,
    ).first()
    if social:
        user = db.get(User, social.user_id)
        if user:
            _maybe_update_consultant_nickname(db, user, username)
            return user

    uname = f"telegram_{telegram_id}"
    user = db.query(User).filter(User.username == uname).first()
    if not user:
        user = User(
            username=uname,
            email=f"{uname}@telegram.user",
            password=hash_password(secrets.token_urlsafe(32)),
            first_name=first_name or "",
            is_active=True,
            date_joined=datetime.utcnow(),
        )
        db.add(user)
        db.flush()
        _ensure_social_account(
            db,
            user_id=user.id,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )

    if register_fio and register_phone and not db.query(Consultant).filter(Consultant.user_id == user.id).first():
        fn, ln, mn = parse_fio(register_fio)
        category = db.query(Category).filter(Category.name_category == "Общая").first()
        if not category:
            category = Category(name_category="Общая")
            db.add(category)
            db.flush()
        consultant = Consultant(
            user_id=user.id,
            first_name=fn,
            last_name=ln,
            middle_name=mn,
            email=user.email or "",
            phone=register_phone,
            telegram_nickname=username or "",
            category_of_specialist_id=category.id,
        )
        db.add(consultant)
        db.flush()
        # Stub only - notifications require explicit connect_spec / Integrations
        db.add(Integration(consultant_id=consultant.id))
    else:
        _maybe_update_consultant_nickname(db, user, username)

    _ensure_social_account(
        db,
        user_id=user.id,
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )

    return user


def confirm_login_via_bot(
    db: Session,
    token: str,
    telegram_id: int | str,
    username: str = "",
    first_name: str = "",
) -> tuple[bool, str, TelegramLoginRequest | None]:
    req = get_active_login_request(db, token)
    if not req:
        return False, "Ссылка недействительна или истекла", None

    tg_id = str(int(telegram_id))
    user: User | None = None

    if req.process == "connect" and req.connect_user_id:
        user = db.get(User, req.connect_user_id)
        if not user:
            return False, "Пользователь не найден", None
        existing = db.query(SocialAccount).filter(
            SocialAccount.provider == "telegram",
            SocialAccount.uid == tg_id,
        ).first()
        if existing and existing.user_id != user.id:
            return False, "Этот аккаунт Телеграм уже привязан к другому пользователю", None
        if not existing:
            db.add(
                SocialAccount(
                    provider="telegram",
                    uid=tg_id,
                    user_id=user.id,
                    extra_data=json.dumps({"username": username, "first_name": first_name}),
                )
            )
        # Phase 4: connect = SocialAccount only. Do not touch Integration.telegram_chat_id.
        if username:
            consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
            if consultant:
                consultant.telegram_nickname = username
    else:
        user = _find_or_create_user_for_telegram(
            db,
            tg_id,
            username,
            first_name,
            req.register_fio,
            req.register_phone,
        )

    req.telegram_id = tg_id
    req.user_id = user.id
    req.complete_token = uuid.uuid4().hex
    req.completed = True
    db.commit()
    db.refresh(req)
    return True, "OK", req


def get_completed_login(db: Session, complete_token: str) -> TelegramLoginRequest | None:
    req = db.query(TelegramLoginRequest).filter(
        TelegramLoginRequest.complete_token == complete_token,
        TelegramLoginRequest.completed.is_(True),
        TelegramLoginRequest.consumed_at.is_(None),
    ).first()
    if not req or req.expires_at < datetime.utcnow():
        return None
    return req


def consume_completed_login(db: Session, req: TelegramLoginRequest) -> None:
    req.consumed_at = datetime.utcnow()
    req.complete_token = None
    db.commit()
