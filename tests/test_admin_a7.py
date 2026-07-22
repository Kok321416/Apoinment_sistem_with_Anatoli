"""Admin A7: Ctrl+K search and session invalidation."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import User
from app.services.platform_admin_search import admin_global_search
from app.services.session_invalidation import invalidate_user_sessions


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _staff(db):
    u = User(
        username="admin",
        password="x",
        email="admin@t.c",
        date_joined=datetime.now(),
        is_staff=True,
        is_superuser=True,
    )
    db.add(u)
    db.commit()
    return u


def test_global_search_finds_user_by_email():
    db = _session()
    admin = _staff(db)
    target = User(username="u@t.c", password="x", email="u@t.c", date_joined=datetime.now())
    db.add(target)
    db.commit()
    from app.auth.session import AuthUser

    auth = AuthUser(
        id=admin.id,
        username=admin.username,
        email=admin.email,
        first_name="",
        last_name="",
        is_active=True,
        password_hash="x",
        is_staff=True,
        is_superuser=True,
    )
    results = admin_global_search(db, auth, "u@t.c")
    assert any(r["type"] == "user" and r["id"] == target.id for r in results)
    db.close()


def test_invalidate_sessions_bumps_version():
    db = _session()
    u = User(username="x", password="x", email="x@t.c", date_joined=datetime.now(), session_version=0)
    db.add(u)
    db.commit()
    updated, err = invalidate_user_sessions(db, u.id)
    assert not err and updated.session_version == 1
    db.close()


def test_session_version_blocks_stale_cookie():
    from app.auth.session import AuthUser, user_from_model

    db = _session()
    u = User(
        username="x",
        password="x",
        email="x@t.c",
        date_joined=datetime.now(),
        is_active=True,
        session_version=2,
    )
    db.add(u)
    db.commit()

    class FakeSession(dict):
        pass

    class FakeRequest:
        scope = {"session": True}

        def __init__(self):
            self.session = FakeSession({"user_id": u.id, "session_version": 1})

    from app.auth import session as session_mod

    assert session_mod.get_current_user(FakeRequest(), db) is None
    u.session_version = 1
    db.commit()
    assert session_mod.get_current_user(FakeRequest(), db) is not None
    db.close()


def test_public_templates_hide_platform_admin_nav():
    """Admin URL is direct-only; no links in public site chrome (except impersonate stop)."""
    from pathlib import Path

    templates = Path(__file__).resolve().parents[1] / "app" / "templates"
    allowed = {"layouts/app.html"}  # stop-impersonate POST only
    offenders = []
    for path in templates.rglob("*.html"):
        rel = path.relative_to(templates).as_posix()
        if rel.startswith("platform_admin/"):
            continue
        if "/platform-admin/" in path.read_text(encoding="utf-8") and rel not in allowed:
            offenders.append(rel)
    assert not offenders, f"platform-admin links in public templates: {offenders}"
