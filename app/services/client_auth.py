"""Phone-based client login helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_, select

from app.deps import normalize_phone
from app.models import ClientCard, Consultant, SocialAccount, User


def normalize_telegram_username(raw: str | None) -> str:
    return (raw or "").strip().lstrip("@").lower()


def login_identifier_to_username(raw: str | None) -> str:
    """Map login form input to User.username (normalized phone or lowercased email)."""
    text = (raw or "").strip()
    phone = normalize_phone(text)
    if phone:
        return phone
    return text.lower()


async def find_user_by_login_async(db, raw: str | None) -> User | None:
    username = login_identifier_to_username(raw)
    if not username:
        return None
    return (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()


async def resolve_client_user_id_by_phone_async(db, phone: str) -> int | None:
    """Return auth user id when phone belongs to a client account (not a specialist)."""
    if not phone:
        return None
    user = (await db.execute(select(User).where(User.username == phone))).scalar_one_or_none()
    if not user:
        return None
    has_consultant = (
        await db.execute(select(Consultant.id).where(Consultant.user_id == user.id).limit(1))
    ).first()
    if has_consultant:
        return None
    return user.id


async def lookup_returning_client_async(
    db,
    *,
    phone: str = "",
    telegram: str = "",
    consultant_id: int | None = None,
) -> dict[str, Any] | None:
    """Find prior client contact data by phone or Telegram @username for autofill."""
    phone_n = normalize_phone(phone)
    tg_n = normalize_telegram_username(telegram)

    if phone_n:
        user = (await db.execute(select(User).where(User.username == phone_n))).scalar_one_or_none()
        if user:
            has_consultant = (
                await db.execute(select(Consultant.id).where(Consultant.user_id == user.id).limit(1))
            ).first()
            if not has_consultant:
                tg = await _telegram_username_for_user_async(db, user.id)
                name = _user_display_name(user)
                return {
                    "found": True,
                    "name": name,
                    "phone": phone_n,
                    "telegram": tg,
                    "message": "Вы уже заходили — данные подставлены автоматически.",
                }

        if consultant_id:
            card = await _client_card_by_phone_async(db, consultant_id, phone_n)
            if card:
                return {
                    "found": True,
                    "name": (card.name or "").strip(),
                    "phone": (card.phone or phone_n).strip(),
                    "telegram": _card_telegram_username(card.telegram),
                    "message": "Вы уже записывались к этому специалисту — данные подставлены.",
                }

    if tg_n:
        if consultant_id:
            card = await _client_card_by_telegram_async(db, consultant_id, tg_n)
            if card:
                return {
                    "found": True,
                    "name": (card.name or "").strip(),
                    "phone": (card.phone or "").strip(),
                    "telegram": tg_n,
                    "message": "Вы уже записывались к этому специалисту — данные подставлены.",
                }

        user_id = await _user_id_by_telegram_username_async(db, tg_n)
        if user_id:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user:
                has_consultant = (
                    await db.execute(select(Consultant.id).where(Consultant.user_id == user.id).limit(1))
                ).first()
                if not has_consultant:
                    return {
                        "found": True,
                        "name": _user_display_name(user),
                        "phone": normalize_phone(user.username) or "",
                        "telegram": tg_n,
                        "message": "Вы уже заходили — данные подставлены автоматически.",
                    }

    return None


def _user_display_name(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    name = f"{first} {last}".strip()
    if name:
        return name
    if hasattr(user, "get_full_name"):
        name = (user.get_full_name() or "").strip()
        if name:
            return name
    return (user.username or "Клиент").strip()


def _card_telegram_username(raw: str | None) -> str:
    tg = (raw or "").strip().lstrip("@")
    if tg.startswith("user:"):
        return ""
    return tg


async def _client_card_by_phone_async(db, consultant_id: int, phone: str) -> ClientCard | None:
    return (
        await db.execute(
            select(ClientCard)
            .where(ClientCard.consultant_id == consultant_id, ClientCard.phone == phone)
            .order_by(ClientCard.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _client_card_by_telegram_async(db, consultant_id: int, tg_n: str) -> ClientCard | None:
    like = f"%{tg_n}%"
    return (
        await db.execute(
            select(ClientCard)
            .where(
                ClientCard.consultant_id == consultant_id,
                or_(ClientCard.telegram.ilike(like), ClientCard.telegram.ilike(f"%@{tg_n}%")),
            )
            .order_by(ClientCard.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _telegram_username_for_user_async(db, user_id: int) -> str:
    sa = (
        await db.execute(
            select(SocialAccount).where(
                SocialAccount.user_id == user_id,
                SocialAccount.provider == "telegram",
            )
        )
    ).scalar_one_or_none()
    if not sa:
        return ""
    try:
        extra = json.loads(sa.extra_data or "{}")
        username = normalize_telegram_username(extra.get("username"))
        if username:
            return username
    except Exception:
        pass
    return ""


async def _user_id_by_telegram_username_async(db, tg_n: str) -> int | None:
    rows = (
        await db.execute(
            select(SocialAccount.user_id, SocialAccount.extra_data).where(
                SocialAccount.provider == "telegram"
            )
        )
    ).all()
    for user_id, extra_raw in rows:
        try:
            extra = json.loads(extra_raw or "{}")
            if normalize_telegram_username(extra.get("username")) == tg_n:
                return int(user_id)
        except Exception:
            continue
    return None
