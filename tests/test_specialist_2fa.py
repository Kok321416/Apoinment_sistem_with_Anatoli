"""Specialist opt-in TOTP 2FA."""
from datetime import datetime
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.login_flow import needs_login_2fa, verify_login_2fa
from app.database import Base
from app.models import Category, Consultant, User, UserTwoFactor
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


def _user_and_consultant(db):
    cat = Category(name_category="Test")
    db.add(cat)
    db.flush()
    user = User(
        username="spec2fa@example.com",
        email="spec2fa@example.com",
        password="x",
        is_active=True,
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


def test_verify_totp_window():
    secret = "JBSWY3DPEHPK3PXP"
    code = totp_at(secret, int(time.time()) // 30)
    assert verify_totp(secret, code)
