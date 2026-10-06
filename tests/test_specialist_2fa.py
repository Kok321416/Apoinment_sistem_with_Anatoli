"""Specialist opt-in TOTP 2FA."""
from datetime import datetime
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.login_flow import needs_login_2fa, verify_login_2fa
from app.auth.session import clear_oauth_state
from app.database import Base
from app.models import AdminTwoFactor, Category, Consultant, User, UserTwoFactor
from app.services.specialist_totp import enable_specialist_2fa, needs_specialist_2fa, specialist_2fa_enabled
from app.services.totp_crypto import totp_at, verify_totp


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _user_and_consultant(db, *, staff: bool = False):
    cat = Category(name_category="Test")
    db.add(cat)
    db.flush()
    user = User(
        username="spec2fa@example.com",
        email="spec2fa@example.com",
        password="x",
        is_active=True,
        is_staff=staff,
        is_superuser=staff,
        date_joined=datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    db.add(
        Consultant(
            user_id=user.id,
            first_name="A",
            last_name="B",
            email=user.email,
            phone="+70000000000",
            category_of_specialist_id=cat.id,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def test_specialist_2fa_opt_in_flow():
    db = _session()
    user = _user_and_consultant(db)
    assert not needs_specialist_2fa(db, user)

    ok, _ = enable_specialist_2fa(db, user, "000000")
    assert not ok

    row = db.get(UserTwoFactor, user.id)
    assert row is not None
    code = totp_at(row.secret, int(time.time()) // 30)
    ok, msg = enable_specialist_2fa(db, user, code)
    assert ok, msg
    assert specialist_2fa_enabled(db, user.id)
    assert needs_login_2fa(db, user)
    assert verify_login_2fa(db, user, code)
    assert not verify_login_2fa(db, user, "111111")
    db.close()


def test_cabinet_login_ignores_admin_totp_when_both_enabled():
    """Admin TOTP must not unlock cabinet/Mini App login (no OR-mix)."""
    db = _session()
    user = _user_and_consultant(db, staff=True)
    row = UserTwoFactor(
        user_id=user.id,
        secret="JBSWY3DPEHPK3PXP",
        enabled=True,
        created_at=datetime.utcnow(),
    )
    admin_row = AdminTwoFactor(
        user_id=user.id,
        secret="KRSXG5CTMVRXEZLU",
        enabled=True,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.add(admin_row)
    db.commit()

    assert needs_login_2fa(db, user)
    admin_code = totp_at(admin_row.secret, int(time.time()) // 30)
    spec_code = totp_at(row.secret, int(time.time()) // 30)
    assert not verify_login_2fa(db, user, admin_code)
    assert verify_login_2fa(db, user, spec_code)
    db.close()


def test_admin_only_2fa_does_not_block_cabinet_login():
    """Platform-admin 2FA is parked; cabinet login must not require it alone."""
    db = _session()
    user = _user_and_consultant(db, staff=True)
    db.add(
        AdminTwoFactor(
            user_id=user.id,
            secret="KRSXG5CTMVRXEZLU",
            enabled=True,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    assert not needs_login_2fa(db, user)
    assert verify_login_2fa(db, user, "000000")
    db.close()


def test_clear_oauth_state_removes_provider_keys():
    class _Req:
        def __init__(self):
            self.scope = {"session": True}
            self.session = {
                "user_id": 1,
                "yandex_oauth_state": "abc",
                "vk_oauth_next": "/x",
                "integrations_success": "ok",
                "yandex_oauth_custom": "keep-prefix",
            }

    req = _Req()
    clear_oauth_state(req)
    assert req.session.get("user_id") == 1
    assert "yandex_oauth_state" not in req.session
    assert "vk_oauth_next" not in req.session
    assert "integrations_success" not in req.session
    assert "yandex_oauth_custom" not in req.session


def test_verify_totp_window():
    secret = "JBSWY3DPEHPK3PXP"
    code = totp_at(secret, int(time.time()) // 30)
    assert verify_totp(secret, code)
