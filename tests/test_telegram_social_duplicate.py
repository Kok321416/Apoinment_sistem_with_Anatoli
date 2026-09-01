"""Telegram login must survive duplicate SocialAccount races."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import SocialAccount, User
from app.services.telegram_auth import (
    _ensure_social_account,
    confirm_login_via_bot,
    create_login_request,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_ensure_social_account_returns_existing_on_duplicate():
    db = _session()
    owner = User(username="owner", password="x", email="o@t.c", date_joined=datetime.now())
    other = User(username="other", password="x", email="a@t.c", date_joined=datetime.now())
    db.add_all([owner, other])
    db.flush()
    db.add(
        SocialAccount(
            provider="telegram",
            uid="951479323",
            user_id=owner.id,
            extra_data="{}",
        )
    )
    db.commit()

    social = _ensure_social_account(
        db,
        user_id=other.id,
        telegram_id="951479323",
        username="@mememelolik",
        first_name="Вероника",
    )
    assert social.user_id == owner.id
    assert db.query(SocialAccount).filter(SocialAccount.uid == "951479323").count() == 1
    db.close()


def test_login_uses_existing_telegram_user_when_phone_user_conflicts():
    db = _session()
    tg_user = User(
        username="telegram_951479323",
        password="x",
        email="tg@telegram.user",
        date_joined=datetime.now(),
        is_active=True,
    )
    phone_user = User(
        username="+79991234567",
        password="x",
        email="",
        date_joined=datetime.now(),
        is_active=True,
    )
    db.add_all([tg_user, phone_user])
    db.flush()
    db.add(
        SocialAccount(
            provider="telegram",
            uid="951479323",
            user_id=tg_user.id,
            extra_data="{}",
        )
    )
    db.commit()

    req = create_login_request(db, process="login", next_url="/tg/")
    ok, msg, out = confirm_login_via_bot(
        db,
        req.token,
        telegram_id=951479323,
        username="mememelolik",
        first_name="Вероника",
    )
    assert ok, msg
    assert out is not None
    assert out.user_id == tg_user.id
    db.close()


@pytest.mark.asyncio
async def test_ensure_social_account_async_returns_existing_on_duplicate():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.services.telegram_auth import _ensure_social_account_async

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        owner = User(username="owner", password="x", email="o@t.c", date_joined=datetime.now())
        other = User(username="other", password="x", email="a@t.c", date_joined=datetime.now())
        db.add_all([owner, other])
        await db.flush()
        db.add(
            SocialAccount(
                provider="telegram",
                uid="951479323",
                user_id=owner.id,
                extra_data="{}",
            )
        )
        await db.commit()

        social = await _ensure_social_account_async(
            db,
            user_id=other.id,
            telegram_id="951479323",
            username="@mememelolik",
            first_name="Вероника",
        )
        assert social.user_id == owner.id

    await engine.dispose()
