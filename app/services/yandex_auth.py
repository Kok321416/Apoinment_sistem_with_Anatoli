"""Yandex ID OAuth login and account linking."""
import json
import logging
import secrets
from datetime import datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import get_settings
from app.models import Category, Consultant, SocialAccount, User
from app.services.bookings import parse_fio
from app.services.email_verification import ensure_email_address

logger = logging.getLogger(__name__)
settings = get_settings()

YANDEX_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"
YANDEX_USER_INFO_URL = "https://login.yandex.ru/info"


def yandex_oauth_configured() -> bool:
    return bool(settings.yandex_oauth_client_id and settings.yandex_oauth_client_secret)


def yandex_redirect_uri() -> str:
    return f"{settings.site_url.rstrip('/')}/accounts/yandex/callback/"


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.yandex_oauth_client_id,
        "redirect_uri": yandex_redirect_uri(),
        "state": state,
        "force_confirm": "yes",
    }
    return f"{YANDEX_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict | None:
    try:
        response = httpx.post(
            YANDEX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.yandex_oauth_client_id,
                "client_secret": settings.yandex_oauth_client_secret,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception("Yandex token exchange failed")
        return None


def fetch_yandex_profile(access_token: str) -> dict | None:
    try:
        response = httpx.get(
            YANDEX_USER_INFO_URL,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception("Yandex user info request failed")
        return None


def _profile_extra(profile: dict) -> dict:
    return {
        "login": (profile.get("login") or "").strip(),
        "first_name": (profile.get("first_name") or "").strip(),
        "last_name": (profile.get("last_name") or "").strip(),
        "display_name": (profile.get("display_name") or "").strip(),
        "default_email": (profile.get("default_email") or "").strip().lower(),
    }


def _sync_user_email_from_yandex(db: Session, user: User, email: str) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    if not user.email or user.email.endswith("@yandex.user") or user.email.endswith("@telegram.user"):
        user.email = email
    if "@" in email and (not user.username or user.username.startswith("yandex_") or user.username.startswith("telegram_")):
        existing = db.query(User).filter(User.username == email, User.id != user.id).first()
        if not existing:
            user.username = email
    ensure_email_address(db, user, email, verified=True)
    user.is_active = True


def _create_consultant_from_register(
    db: Session,
    user: User,
    register_fio: str,
    register_phone: str,
    email: str,
) -> None:
    if db.query(Consultant).filter(Consultant.user_id == user.id).first():
        return
    first_name, last_name, middle_name = parse_fio(register_fio)
    category = db.query(Category).filter(Category.name_category == "Общая").first()
    if not category:
        category = Category(name_category="Общая")
        db.add(category)
        db.flush()
    db.add(Consultant(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        email=email or user.email or "",
        phone=register_phone,
        telegram_nickname="",
        category_of_specialist_id=category.id,
    ))


def _create_yandex_user(
    db: Session,
    yandex_id: str,
    profile: dict,
    extra: dict,
) -> User:
    email = extra["default_email"]
    first_name = extra["first_name"]
    last_name = extra["last_name"]
    username = email or f"yandex_{yandex_id}"
    if db.query(User).filter(User.username == username).first():
        username = f"yandex_{yandex_id}"

    user = User(
        username=username,
        email=email or f"yandex_{yandex_id}@yandex.user",
        password=hash_password(secrets.token_urlsafe(32)),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        date_joined=datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    db.add(SocialAccount(
        provider="yandex",
        uid=yandex_id,
        user_id=user.id,
        extra_data=json.dumps(extra, ensure_ascii=False),
    ))
    _sync_user_email_from_yandex(db, user, email)
    return user


def _link_yandex_account(db: Session, user: User, yandex_id: str, extra: dict) -> str | None:
    existing = db.query(SocialAccount).filter(
        SocialAccount.provider == "yandex",
        SocialAccount.uid == yandex_id,
    ).first()
    if existing and existing.user_id != user.id:
        return "Этот аккаунт Яндекс уже привязан к другому пользователю"
    if not existing:
        db.add(SocialAccount(
            provider="yandex",
            uid=yandex_id,
            user_id=user.id,
            extra_data=json.dumps(extra, ensure_ascii=False),
        ))
    _sync_user_email_from_yandex(db, user, extra["default_email"])
    return None


def complete_yandex_oauth(
    db: Session,
    *,
    process: str,
    profile: dict,
    register_fio: str | None,
    register_phone: str | None,
    connect_user_id: int | None,
) -> tuple[User | None, str | None]:
    yandex_id = str(profile.get("id") or "").strip()
    if not yandex_id:
        return None, "Не удалось получить профиль Яндекса"

    extra = _profile_extra(profile)
    existing_social = db.query(SocialAccount).filter(
        SocialAccount.provider == "yandex",
        SocialAccount.uid == yandex_id,
    ).first()

    if process == "connect":
        if not connect_user_id:
            return None, "Требуется авторизация"
        user = db.get(User, connect_user_id)
        if not user:
            return None, "Пользователь не найден"
        err = _link_yandex_account(db, user, yandex_id, extra)
        if err:
            return None, err
        db.commit()
        return user, None

    if existing_social:
        user = db.get(User, existing_social.user_id)
        if not user:
            return None, "Пользователь не найден"
        _sync_user_email_from_yandex(db, user, extra["default_email"])
        db.commit()
        return user, None

    if process == "signup":
        if not register_fio or not register_phone:
            return None, "Укажите ФИО и телефон перед регистрацией через Яндекс"
        user = _create_yandex_user(db, yandex_id, profile, extra)
        _create_consultant_from_register(db, user, register_fio, register_phone, extra["default_email"])
        db.commit()
        return user, None

    return None, "Аккаунт не найден. Сначала зарегистрируйтесь."
