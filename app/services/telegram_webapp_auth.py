"""Telegram Mini App initData validation and session login (Phase 8)."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from urllib.parse import parse_qsl

from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import get_settings
from app.models import SocialAccount, User
from app.services.telegram_auth import _ensure_social_account, _maybe_update_consultant_nickname

# Reject stale initData (default 24h).
DEFAULT_MAX_AGE_SECONDS = 86400


def validate_webapp_init_data(
    init_data: str,
    *,
    bot_token: str | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict | None:
    """
    Validate Telegram WebApp initData signature.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    raw = (init_data or "").strip()
    if not raw:
        return None
    token = (bot_token if bot_token is not None else get_settings().telegram_bot_token) or ""
    if not token:
        return None

    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = (pairs.pop("hash", None) or "").strip()
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        auth_date = int(pairs.get("auth_date") or "0")
    except ValueError:
        return None
    if max_age_seconds > 0 and auth_date > 0:
        if abs(int(time.time()) - auth_date) > max_age_seconds:
            return None

    user_raw = pairs.get("user")
    user_obj: dict = {}
    if user_raw:
        try:
            parsed = json.loads(user_raw)
            if isinstance(parsed, dict):
                user_obj = parsed
        except (TypeError, json.JSONDecodeError):
            return None

    return {
        "auth_date": auth_date,
        "query_id": pairs.get("query_id"),
        "user": user_obj,
        "raw": pairs,
    }


def find_or_create_user_from_webapp(db: Session, tg_user: dict) -> User | None:
    """Find SocialAccount by Telegram id or create a client User (no Consultant)."""
    tid = tg_user.get("id")
    if tid is None:
        return None
    try:
        telegram_id = str(int(tid))
    except (TypeError, ValueError):
        return None

    username = (tg_user.get("username") or "").strip()
    if username and not username.startswith("@"):
        username = "@" + username
    first_name = (tg_user.get("first_name") or "").strip()
    last_name = (tg_user.get("last_name") or "").strip()

    social = (
        db.query(SocialAccount)
        .filter(SocialAccount.provider == "telegram", SocialAccount.uid == telegram_id)
        .first()
    )
    if social:
        user = db.get(User, social.user_id)
        if user and user.is_active:
            _maybe_update_consultant_nickname(db, user, username)
            if first_name and not (user.first_name or "").strip():
                user.first_name = first_name
            if last_name and not (user.last_name or "").strip():
                user.last_name = last_name
            db.commit()
            return user
        return None

    uname = f"telegram_{telegram_id}"
    user = db.query(User).filter(User.username == uname).first()
    if not user:
        user = User(
            username=uname,
            email=f"{uname}@telegram.user",
            password=hash_password(secrets.token_urlsafe(32)),
            first_name=first_name,
            last_name=last_name,
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
    _maybe_update_consultant_nickname(db, user, username)
    db.commit()
    db.refresh(user)
    return user
