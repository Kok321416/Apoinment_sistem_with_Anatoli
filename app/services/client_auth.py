"""Phone-based client login helpers."""

from __future__ import annotations

from sqlalchemy import select

from app.deps import normalize_phone
from app.models import Consultant, User


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
