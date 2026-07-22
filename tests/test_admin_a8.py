"""Admin A8: SSE KPI, RBAC home redirect, filtered Ctrl+K shortcuts."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import User
from app.services.admin_rbac import ROLE_DEVELOPER, ROLE_SUPPORT, assign_role
from app.services.platform_admin_access import admin_home_url
from app.services.platform_admin_search import admin_global_search


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _auth(user: User):
    from app.auth.session import AuthUser

    return AuthUser(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name="",
        last_name="",
        is_active=True,
        password_hash="x",
        is_staff=user.is_staff,
        is_superuser=user.is_superuser,
    )


def test_nav_shortcuts_filtered_for_support_role():
    db = _session()
    staff = User(
        username="sup",
        password="x",
        email="s@t.c",
        date_joined=datetime.now(),
        is_staff=True,
    )
    db.add(staff)
    db.commit()
    assign_role(db, user_id=staff.id, role=ROLE_SUPPORT, granted_by=1)
    results = admin_global_search(db, _auth(staff), "")
    titles = {r["title"] for r in results}
    assert "Поддержка" in titles
    assert "Telegram" not in titles
    assert "Ops" not in titles
    db.close()


def test_nav_shortcuts_filtered_for_developer_role():
    db = _session()
    staff = User(
        username="dev",
        password="x",
        email="d@t.c",
        date_joined=datetime.now(),
        is_staff=True,
    )
    db.add(staff)
    db.commit()
    assign_role(db, user_id=staff.id, role=ROLE_DEVELOPER, granted_by=1)
    results = admin_global_search(db, _auth(staff), "")
    titles = {r["title"] for r in results}
    assert "Ошибки" in titles
    assert "Ops" in titles
    assert "Пользователи" not in titles
    db.close()


def test_admin_home_url_for_developer():
    db = _session()
    staff = User(
        username="dev",
        password="x",
        email="d@t.c",
        date_joined=datetime.now(),
        is_staff=True,
    )
    db.add(staff)
    db.commit()
    assign_role(db, user_id=staff.id, role=ROLE_DEVELOPER, granted_by=1)
    assert admin_home_url(db, _auth(staff)) == "/platform-admin/errors/"
    db.close()


def test_kpi_stream_route_registered():
    from app.main import app

    paths = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.append(path)
    assert "/platform-admin/api/kpi/stream/" in paths
