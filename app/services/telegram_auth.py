"""Telegram bot login flow (without Login Widget)."""
import json
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.deps import normalize_phone
from app.config import get_settings
from app.models import Consultant, SocialAccount, TelegramLoginRequest, User
from app.services.consultant_onboarding import (
    apply_user_names_from_fio,
    create_consultant_for_user,
    create_consultant_for_user_async,
)

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
    client_channel: str = "web",
) -> TelegramLoginRequest:
    from app.services.client_channel import normalize_client_channel

    now = datetime.utcnow()
    req = TelegramLoginRequest(
        token=secrets.token_urlsafe(24),
        next_url=_safe_next_url(next_url),
        process=process,
        register_fio=(register_fio or "").strip() or None,
        register_phone=normalize_phone(register_phone) or None,
        connect_user_id=connect_user_id,
        client_channel=normalize_client_channel(client_channel),
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
        if existing.user_id != user_id:
            return
        extra = json.dumps({"username": username, "first_name": first_name})
        if existing.extra_data != extra:
            existing.extra_data = extra
        return
    db.add(
        SocialAccount(
            provider="telegram",
            uid=telegram_id,
            user_id=user_id,
            extra_data=json.dumps({"username": username, "first_name": first_name}),
        )
    )
    db.flush()


def _maybe_update_consultant_nickname(db: Session, user: User, username: str) -> None:
    if not username:
        return
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
    if consultant and not (consultant.telegram_nickname or "").strip():
        consultant.telegram_nickname = username


def _wants_specialist_profile(process: str, register_fio: str | None, register_phone: str | None) -> bool:
    settings = get_settings()
    if settings.force_consultant_on_signup:
        return bool(register_fio and register_phone)
    if process == "signup_client":
        return False
    # Legacy signup / login with register fields = specialist
    return bool(register_fio and register_phone)


def _find_or_create_user_for_telegram(
    db: Session,
    telegram_id: str,
    username: str,
    first_name: str,
    register_fio: str | None,
    register_phone: str | None,
    *,
    process: str = "login",
) -> User:
    """
    Login/signup via Telegram.

    Phase 4: does NOT write Integration.telegram_chat_id.
    Phase 5: specialist profile only when signup (not signup_client) or FORCE_CONSULTANT_ON_SIGNUP.
    """
    social = db.query(SocialAccount).filter(
        SocialAccount.provider == "telegram",
        SocialAccount.uid == telegram_id,
    ).first()
    if social:
        user = db.get(User, social.user_id)
        if user:
            _maybe_update_consultant_nickname(db, user, username)
            if _wants_specialist_profile(process, register_fio, register_phone):
                create_consultant_for_user(
                    db, user, fio=register_fio or "", phone=register_phone or "", email=user.email
                )
            elif register_fio:
                apply_user_names_from_fio(user, register_fio)
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

    if _wants_specialist_profile(process, register_fio, register_phone):
        create_consultant_for_user(
            db, user, fio=register_fio or "", phone=register_phone or "", email=user.email
        )
    else:
        if register_fio:
            apply_user_names_from_fio(user, register_fio)
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
            _ensure_social_account(
                db,
                user_id=user.id,
                telegram_id=tg_id,
                username=username,
                first_name=first_name,
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
            process=req.process or "login",
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


async def create_login_request_async(
    db,
    *,
    next_url: str = "/",
    process: str = "login",
    register_fio: str | None = None,
    register_phone: str | None = None,
    connect_user_id: int | None = None,
    client_channel: str = "web",
) -> TelegramLoginRequest:
    from app.services.client_channel import normalize_client_channel

    now = datetime.utcnow()
    req = TelegramLoginRequest(
        token=secrets.token_urlsafe(24),
        next_url=_safe_next_url(next_url),
        process=process,
        register_fio=(register_fio or "").strip() or None,
        register_phone=normalize_phone(register_phone) or None,
        connect_user_id=connect_user_id,
        client_channel=normalize_client_channel(client_channel),
        created_at=now,
        expires_at=now + timedelta(minutes=LOGIN_TTL_MINUTES),
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def get_active_login_request_async(db, token: str) -> TelegramLoginRequest | None:
    from sqlalchemy import select

    req = (
        await db.execute(select(TelegramLoginRequest).where(TelegramLoginRequest.token == token))
    ).scalar_one_or_none()
    if not req or req.completed:
        return None
    if req.expires_at < datetime.utcnow():
        return None
    return req


async def _ensure_social_account_async(
    db,
    *,
    user_id: int,
    telegram_id: str,
    username: str,
    first_name: str,
) -> None:
    from sqlalchemy import select

    existing = (
        await db.execute(
            select(SocialAccount).where(
                SocialAccount.provider == "telegram",
                SocialAccount.uid == telegram_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.user_id != user_id:
            return
        extra = json.dumps({"username": username, "first_name": first_name})
        if existing.extra_data != extra:
            existing.extra_data = extra
        return
    db.add(
        SocialAccount(
            provider="telegram",
            uid=telegram_id,
            user_id=user_id,
            extra_data=json.dumps({"username": username, "first_name": first_name}),
        )
    )
    await db.flush()


async def _maybe_update_consultant_nickname_async(db, user: User, username: str) -> None:
    from sqlalchemy import select

    if not username:
        return
    consultant = (
        await db.execute(select(Consultant).where(Consultant.user_id == user.id))
    ).scalar_one_or_none()
    if consultant and not (consultant.telegram_nickname or "").strip():
        consultant.telegram_nickname = username


async def _find_or_create_user_for_telegram_async(
    db,
    telegram_id: str,
    username: str,
    first_name: str,
    register_fio: str | None,
    register_phone: str | None,
    *,
    process: str = "login",
) -> User:
    from sqlalchemy import select

    social = (
        await db.execute(
            select(SocialAccount).where(
                SocialAccount.provider == "telegram",
                SocialAccount.uid == telegram_id,
            )
        )
    ).scalar_one_or_none()
    if social:
        user = await db.get(User, social.user_id)
        if user:
            await _maybe_update_consultant_nickname_async(db, user, username)
            if _wants_specialist_profile(process, register_fio, register_phone):
                await create_consultant_for_user_async(
                    db, user, fio=register_fio or "", phone=register_phone or "", email=user.email
                )
            elif register_fio:
                apply_user_names_from_fio(user, register_fio)
            return user

    uname = f"telegram_{telegram_id}"
    user = (
        await db.execute(select(User).where(User.username == uname))
    ).scalar_one_or_none()
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
        await db.flush()

    if _wants_specialist_profile(process, register_fio, register_phone):
        await create_consultant_for_user_async(
            db, user, fio=register_fio or "", phone=register_phone or "", email=user.email
        )
    else:
        if register_fio:
            apply_user_names_from_fio(user, register_fio)
        await _maybe_update_consultant_nickname_async(db, user, username)

    await _ensure_social_account_async(
        db,
        user_id=user.id,
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )

    return user


async def confirm_login_via_bot_async(
    db,
    token: str,
    telegram_id: int | str,
    username: str = "",
    first_name: str = "",
) -> tuple[bool, str, TelegramLoginRequest | None]:
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    req = await get_active_login_request_async(db, token)
    if not req:
        return False, "Ссылка недействительна или истекла", None

    tg_id = str(int(telegram_id))
    user: User | None = None

    try:
        if req.process == "connect" and req.connect_user_id:
            user = await db.get(User, req.connect_user_id)
            if not user:
                return False, "Пользователь не найден", None
            existing = (
                await db.execute(
                    select(SocialAccount).where(
                        SocialAccount.provider == "telegram",
                        SocialAccount.uid == tg_id,
                    )
                )
            ).scalar_one_or_none()
            if existing and existing.user_id != user.id:
                return False, "Этот аккаунт Телеграм уже привязан к другому пользователю", None
            if not existing:
                await _ensure_social_account_async(
                    db,
                    user_id=user.id,
                    telegram_id=tg_id,
                    username=username,
                    first_name=first_name,
                )
            if username:
                consultant = (
                    await db.execute(select(Consultant).where(Consultant.user_id == user.id))
                ).scalar_one_or_none()
                if consultant:
                    consultant.telegram_nickname = username
        else:
            user = await _find_or_create_user_for_telegram_async(
                db,
                tg_id,
                username,
                first_name,
                req.register_fio,
                req.register_phone,
                process=req.process or "login",
            )

        req.telegram_id = tg_id
        req.user_id = user.id
        req.complete_token = uuid.uuid4().hex
        req.completed = True
        await db.commit()
        await db.refresh(req)
        return True, "OK", req
    except IntegrityError:
        await db.rollback()
        req = await get_active_login_request_async(db, token)
        if not req:
            return False, "Ссылка недействительна или истекла", None
        social = (
            await db.execute(
                select(SocialAccount).where(
                    SocialAccount.provider == "telegram",
                    SocialAccount.uid == tg_id,
                )
            )
        ).scalar_one_or_none()
        if not social:
            return False, "Ошибка привязки Telegram, попробуйте снова", None
        user = await db.get(User, social.user_id)
        if not user:
            return False, "Пользователь не найден", None
        req.telegram_id = tg_id
        req.user_id = user.id
        req.complete_token = uuid.uuid4().hex
        req.completed = True
        await db.commit()
        await db.refresh(req)
        return True, "OK", req


async def get_completed_login_async(db, complete_token: str) -> TelegramLoginRequest | None:
    from sqlalchemy import select

    req = (
        await db.execute(
            select(TelegramLoginRequest).where(
                TelegramLoginRequest.complete_token == complete_token,
                TelegramLoginRequest.completed.is_(True),
                TelegramLoginRequest.consumed_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not req or req.expires_at < datetime.utcnow():
        return None
    return req


async def consume_completed_login_async(db, req: TelegramLoginRequest) -> None:
    req.consumed_at = datetime.utcnow()
    req.complete_token = None
    await db.commit()
