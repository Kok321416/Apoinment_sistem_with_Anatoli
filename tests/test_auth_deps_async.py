"""Cabinet auth Depends pieces: session login + Mini App Bearer."""
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.session import get_current_user, login_user
from app.database import Base
from app.models import User
from app.services.miniapp_token import bearer_user_id, mint_miniapp_access_token, read_miniapp_access_token


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_session_cookie_user_resolves_after_login():
    db = _session()
    user = User(
        username="dep@example.com",
        email="dep@example.com",
        password="x",
        is_active=True,
        date_joined=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    req = SimpleNamespace(scope={"session": {}}, session={}, state=SimpleNamespace())
    login_user(req, user)
    auth = get_current_user(req, db)
    assert auth is not None
    assert auth.id == user.id
    db.close()


def test_miniapp_bearer_token_roundtrip():
    db = _session()
    user = User(
        username="bearer@example.com",
        email="bearer@example.com",
        password="x",
        is_active=True,
        date_joined=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = mint_miniapp_access_token(user.id)
    assert read_miniapp_access_token(token) == user.id
    assert bearer_user_id(f"Bearer {token}") == user.id
    assert bearer_user_id("Bearer expired-or-junk") is None
    assert bearer_user_id(None) is None
    db.close()
