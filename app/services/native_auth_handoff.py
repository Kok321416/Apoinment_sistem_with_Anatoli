"""One-time handoff tokens: external OAuth browser → Capacitor WebView session."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import NativeAuthHandoff, User
from app.utils.safe_redirect import safe_next_url

HANDOFF_TTL_MINUTES = 10


def create_native_handoff(db: Session, *, user_id: int, next_url: str | None) -> NativeAuthHandoff:
    now = datetime.utcnow()
    row = NativeAuthHandoff(
        token=secrets.token_urlsafe(24),
        user_id=user_id,
        next_url=safe_next_url(next_url),
        created_at=now,
        expires_at=now + timedelta(minutes=HANDOFF_TTL_MINUTES),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def consume_native_handoff(db: Session, token: str) -> tuple[User | None, str]:
    row = db.query(NativeAuthHandoff).filter(NativeAuthHandoff.token == token).first()
    if not row or row.consumed_at is not None:
        return None, "/"
    if row.expires_at < datetime.utcnow():
        return None, "/"
    user = db.get(User, row.user_id)
    next_url = safe_next_url(row.next_url)
    row.consumed_at = datetime.utcnow()
    db.commit()
    return user, next_url


async def create_native_handoff_async(db, *, user_id: int, next_url: str | None) -> NativeAuthHandoff:
    now = datetime.utcnow()
    row = NativeAuthHandoff(
        token=secrets.token_urlsafe(24),
        user_id=user_id,
        next_url=safe_next_url(next_url),
        created_at=now,
        expires_at=now + timedelta(minutes=HANDOFF_TTL_MINUTES),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def consume_native_handoff_async(db, token: str) -> tuple[User | None, str]:
    from sqlalchemy import select

    row = (
        await db.execute(select(NativeAuthHandoff).where(NativeAuthHandoff.token == token))
    ).scalar_one_or_none()
    if not row or row.consumed_at is not None:
        return None, "/"
    if row.expires_at < datetime.utcnow():
        return None, "/"
    user = await db.get(User, row.user_id)
    next_url = safe_next_url(row.next_url)
    row.consumed_at = datetime.utcnow()
    await db.commit()
    return user, next_url
