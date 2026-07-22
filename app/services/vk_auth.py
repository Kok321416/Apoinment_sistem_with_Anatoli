"""VK ID OAuth login and account linking (PKCE, backend code exchange)."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import get_settings
from app.models import SocialAccount, User
from app.services.email_verification import ensure_email_address

logger = logging.getLogger(__name__)

VK_AUTHORIZE_URL = "https://id.vk.ru/authorize"
VK_TOKEN_URL = "https://id.vk.ru/oauth2/auth"
VK_USER_INFO_URL = "https://id.vk.ru/oauth2/user_info"


def vk_oauth_configured() -> bool:
    settings = get_settings()
    return bool(settings.vk_oauth_client_id)


def vk_messaging_configured() -> bool:
    settings = get_settings()
    return bool(settings.vk_group_id and settings.vk_group_access_token)


def vk_redirect_uri() -> str:
    settings = get_settings()
    return f"{settings.site_url.rstrip('/')}/accounts/vk/callback/"


def vk_group_write_url() -> str | None:
    settings = get_settings()
    gid = (settings.vk_group_id or "").strip().lstrip("-")
    if not gid:
        return None
    return f"https://vk.com/write-{gid}"


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(*, state: str, code_challenge: str) -> str:
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.vk_oauth_client_id,
        "redirect_uri": vk_redirect_uri(),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "email phone vkid.personal_info",
        "lang_id": "0",
    }
    return f"{VK_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(*, code: str, code_verifier: str, device_id: str, state: str) -> dict | None:
    settings = get_settings()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "client_id": settings.vk_oauth_client_id,
        "device_id": device_id,
        "redirect_uri": vk_redirect_uri(),
        "state": state,
    }
    if settings.vk_oauth_client_secret:
        data["client_secret"] = settings.vk_oauth_client_secret
    try:
        response = httpx.post(VK_TOKEN_URL, data=data, timeout=20)
        if response.status_code >= 400:
            logger.error(
                "VK token exchange failed: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return None
        payload = response.json()
        if payload.get("error"):
            logger.error("VK token exchange error payload: %s", payload)
            return None
        return payload
    except Exception:
        logger.exception("VK token exchange failed")
        return None


def fetch_vk_profile(access_token: str) -> dict | None:
    settings = get_settings()
    try:
        response = httpx.post(
            VK_USER_INFO_URL,
            data={
                "access_token": access_token,
                "client_id": settings.vk_oauth_client_id,
            },
            timeout=15,
        )
        if response.status_code >= 400:
            logger.error("VK user_info failed: status=%s body=%s", response.status_code, response.text[:500])
            return None
        payload = response.json()
        user = payload.get("user") if isinstance(payload, dict) else None
        if not user:
            logger.error("VK user_info missing user: %s", payload)
            return None
        return user
    except Exception:
        logger.exception("VK user_info request failed")
        return None


def _profile_extra(profile: dict) -> dict:
    return {
        "first_name": (profile.get("first_name") or "").strip(),
        "last_name": (profile.get("last_name") or "").strip(),
        "email": (profile.get("email") or "").strip().lower(),
        "phone": (profile.get("phone") or "").strip(),
        "avatar": (profile.get("avatar") or "").strip(),
    }


def _sync_user_email_from_vk(db: Session, user: User, email: str) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    placeholder_suffixes = ("@vk.user", "@yandex.user", "@telegram.user")
    if not user.email or any(user.email.endswith(s) for s in placeholder_suffixes):
        user.email = email
    if "@" in email and (
        not user.username
        or user.username.startswith("vk_")
        or user.username.startswith("yandex_")
        or user.username.startswith("telegram_")
    ):
        existing = db.query(User).filter(User.username == email, User.id != user.id).first()
        if not existing:
            user.username = email
    ensure_email_address(db, user, email, verified=True)
    user.is_active = True


def _unique_consultant_email(db: Session, email: str, user: User, vk_id: str) -> str:
    from app.models import Consultant

    candidate = (email or user.email or f"vk_{vk_id}@vk.user").strip().lower()
    if not candidate:
        candidate = f"vk_{vk_id}@vk.user"
    existing = db.query(Consultant).filter(Consultant.email == candidate).first()
    if existing and existing.user_id != user.id:
        candidate = f"vk_{vk_id}@vk.user"
    return candidate


def _create_consultant_from_register(
    db: Session,
    user: User,
    register_fio: str,
    register_phone: str,
    email: str,
    vk_id: str,
) -> None:
    from app.services.consultant_onboarding import create_consultant_for_user

    create_consultant_for_user(
        db,
        user,
        fio=register_fio,
        phone=register_phone,
        email=_unique_consultant_email(db, email, user, vk_id),
    )


def _create_vk_user(db: Session, vk_id: str, extra: dict) -> User:
    email = extra["email"]
    first_name = extra["first_name"]
    last_name = extra["last_name"]
    username = email or f"vk_{vk_id}"
    if db.query(User).filter(User.username == username).first():
        username = f"vk_{vk_id}"

    user = User(
        username=username,
        email=email or f"vk_{vk_id}@vk.user",
        password=hash_password(secrets.token_urlsafe(32)),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        date_joined=datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    db.add(
        SocialAccount(
            provider="vk",
            uid=vk_id,
            user_id=user.id,
            extra_data=json.dumps(extra, ensure_ascii=False),
        )
    )
    _sync_user_email_from_vk(db, user, email)
    return user


def _link_vk_account(db: Session, user: User, vk_id: str, extra: dict) -> str | None:
    existing = db.query(SocialAccount).filter(
        SocialAccount.provider == "vk",
        SocialAccount.uid == vk_id,
    ).first()
    if existing and existing.user_id != user.id:
        return "Этот аккаунт VK уже привязан к другому пользователю"
    if not existing:
        db.add(
            SocialAccount(
                provider="vk",
                uid=vk_id,
                user_id=user.id,
                extra_data=json.dumps(extra, ensure_ascii=False),
            )
        )
    else:
        existing.extra_data = json.dumps(extra, ensure_ascii=False)
    _sync_user_email_from_vk(db, user, extra["email"])
    return None


def complete_vk_oauth(
    db: Session,
    *,
    process: str,
    profile: dict,
    register_fio: str | None,
    register_phone: str | None,
    connect_user_id: int | None,
) -> tuple[User | None, str | None, str | None]:
    """Returns (user, error, vk_user_id)."""
    vk_id = str(profile.get("user_id") or profile.get("id") or "").strip()
    if not vk_id:
        return None, "Не удалось получить профиль VK", None

    extra = _profile_extra(profile)
    existing_social = db.query(SocialAccount).filter(
        SocialAccount.provider == "vk",
        SocialAccount.uid == vk_id,
    ).first()

    try:
        if process == "connect":
            if not connect_user_id:
                return None, "Требуется авторизация", None
            user = db.get(User, connect_user_id)
            if not user:
                return None, "Пользователь не найден", None
            err = _link_vk_account(db, user, vk_id, extra)
            if err:
                return None, err, None
            db.commit()
            return user, None, vk_id

        if existing_social:
            user = db.get(User, existing_social.user_id)
            if not user:
                return None, "Пользователь не найден", None
            _sync_user_email_from_vk(db, user, extra["email"])
            existing_social.extra_data = json.dumps(extra, ensure_ascii=False)
            db.commit()
            return user, None, vk_id

        if process in ("signup", "signup_client"):
            if not register_fio or not register_phone:
                return None, "Укажите ФИО и телефон перед регистрацией через VK", None
            user = _create_vk_user(db, vk_id, extra)
            from app.config import get_settings
            from app.services.consultant_onboarding import apply_user_names_from_fio

            force = get_settings().force_consultant_on_signup
            as_specialist = force or process == "signup"
            if as_specialist:
                _create_consultant_from_register(
                    db,
                    user,
                    register_fio,
                    register_phone,
                    extra["email"],
                    vk_id,
                )
            else:
                apply_user_names_from_fio(user, register_fio)
            db.commit()
            return user, None, vk_id

        return None, "Аккаунт не найден. Сначала зарегистрируйтесь.", None
    except IntegrityError:
        db.rollback()
        logger.exception("VK OAuth DB integrity error during %s", process)
        return None, "Не удалось создать аккаунт. Возможно, почта уже используется.", None
    except Exception:
        db.rollback()
        logger.exception("VK OAuth failed during %s", process)
        return None, "Внутренняя ошибка при входе через VK. Попробуйте позже.", None


def resolve_vk_user_id_for_user(db: Session, user_id: int | None) -> int | None:
    if not user_id:
        return None
    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.provider == "vk", SocialAccount.user_id == user_id)
        .first()
    )
    if not sa or not sa.uid:
        return None
    try:
        return int(sa.uid)
    except (TypeError, ValueError):
        return None
