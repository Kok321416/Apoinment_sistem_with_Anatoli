"""Phase 10 / Admin A0-A1: platform admin + broadcast audience."""
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_db
from app.models import (
    Category,
    Consultant,
    Integration,
    SocialAccount,
    User,
)
from app.services.broadcast import (
    AUDIENCE_ALL,
    AUDIENCE_CLIENTS,
    AUDIENCE_DUAL,
    AUDIENCE_SPECIALISTS,
    AUDIENCE_TEST_SELF,
    create_broadcast_job,
    dry_run_count,
    process_broadcast_jobs,
    resolve_audience_chats,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_resolve_audience_dedup_and_segments():
    db = _session()
    u_spec = User(
        username="spec",
        password="x",
        email="s@t.c",
        date_joined=datetime.now(),
        notify_broadcast=True,
        is_staff=False,
    )
    u_client = User(
        username="cli",
        password="x",
        email="c@t.c",
        date_joined=datetime.now(),
        notify_broadcast=True,
    )
    u_dual = User(
        username="dual",
        password="x",
        email="d@t.c",
        date_joined=datetime.now(),
        notify_broadcast=True,
    )
    db.add_all([u_spec, u_client, u_dual])
    db.flush()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c1 = Consultant(
        first_name="S",
        last_name="P",
        email="s@t.c",
        phone="+1",
        category_of_specialist_id=cat.id,
        user_id=u_spec.id,
    )
    c2 = Consultant(
        first_name="D",
        last_name="U",
        email="d@t.c",
        phone="+2",
        category_of_specialist_id=cat.id,
        user_id=u_dual.id,
    )
    db.add_all([c1, c2])
    db.flush()
    db.add(
        Integration(
            consultant_id=c1.id,
            telegram_chat_id="1001",
            telegram_connected=True,
            telegram_enabled=True,
        )
    )
    db.add(
        Integration(
            consultant_id=c2.id,
            telegram_chat_id="2002",
            telegram_connected=True,
            telegram_enabled=True,
        )
    )
    db.add(SocialAccount(provider="telegram", uid="3003", user_id=u_client.id, extra_data="{}"))
    db.add(SocialAccount(provider="telegram", uid="2002", user_id=u_dual.id, extra_data="{}"))
    db.commit()

    specs = resolve_audience_chats(db, AUDIENCE_SPECIALISTS)
    assert {r["chat_id"] for r in specs} == {"1001", "2002"}

    clients = resolve_audience_chats(db, AUDIENCE_CLIENTS)
    # clients_only excludes specialist chats
    assert {r["chat_id"] for r in clients} == {"3003"}

    dual = resolve_audience_chats(db, AUDIENCE_DUAL)
    assert {r["chat_id"] for r in dual} == {"2002"}

    all_u = resolve_audience_chats(db, AUDIENCE_ALL)
    assert {r["chat_id"] for r in all_u} == {"1001", "2002", "3003"}

    self_chats = resolve_audience_chats(db, AUDIENCE_TEST_SELF, actor_user_id=u_dual.id)
    assert len(self_chats) == 1
    assert self_chats[0]["chat_id"] == "2002"
    db.close()


def test_create_job_and_process_with_mock_send():
    db = _session()
    admin = User(
        username="adm",
        password="x",
        email="a@t.c",
        date_joined=datetime.now(),
        is_staff=True,
        notify_broadcast=True,
    )
    db.add(admin)
    db.flush()
    db.add(SocialAccount(provider="telegram", uid="777", user_id=admin.id, extra_data="{}"))
    db.commit()

    job, err = create_broadcast_job(
        db, created_by=admin.id, audience=AUDIENCE_TEST_SELF, text="Hello <b>test</b>"
    )
    assert err is None
    assert job is not None
    assert job.recipients_total == 1

    with patch("app.services.broadcast.send_telegram_with_retry", return_value=(True, None)):
        stats = process_broadcast_jobs(db, limit_jobs=1, chunk_size=10, sleep_between=0)
    assert stats["sent"] == 1
    db.refresh(job)
    assert job.status == "completed"
    db.close()


def test_platform_admin_gate(monkeypatch):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    from app.auth.session import AuthUser
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "platform_admin_enabled", True)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def _override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    try:
        with patch("app.routers.platform_admin.require_platform_admin") as mock_req:
            mock_req.side_effect = HTTPException(status_code=403, detail="Forbidden")
            r403 = client.get("/platform-admin/")
            assert r403.status_code == 403

        staff_auth = AuthUser(
            id=1,
            username="staff1",
            email="staff@t.c",
            first_name="",
            last_name="",
            is_active=True,
            password_hash="x",
            is_staff=True,
        )
        with patch("app.routers.platform_admin.require_platform_admin", return_value=staff_auth):
            r_ok = client.get("/platform-admin/")
            assert r_ok.status_code == 200
            assert "Admin" in r_ok.text
            r_tg = client.get("/platform-admin/telegram/")
            assert r_tg.status_code == 200
            assert "Telegram" in r_tg.text

        monkeypatch.setattr(settings, "platform_admin_enabled", False)
        # When flag off, require_platform_admin raises 404 - call real gate via unpatch
        from app.deps import require_platform_admin
        from starlette.requests import Request

        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
        # simpler unit check:
        from unittest.mock import MagicMock

        req = MagicMock()
        db = Session()
        try:
            require_platform_admin(req, db)
            assert False, "expected 404"
        except HTTPException as e:
            assert e.status_code == 404
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()
        monkeypatch.setattr(settings, "platform_admin_enabled", False)


def test_dry_run_count_matches_resolve():
    db = _session()
    assert dry_run_count(db, AUDIENCE_SPECIALISTS) == 0
    db.close()
