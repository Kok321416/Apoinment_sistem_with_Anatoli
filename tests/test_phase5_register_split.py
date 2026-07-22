"""Phase 5: client signup without Consultant + become-specialist."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Consultant, Integration, User
from app.services.consultant_onboarding import create_consultant_for_user, find_consultant_for_user
from app.services.telegram_auth import confirm_login_via_bot, create_login_request


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_signup_client_has_no_consultant():
    db = _session()
    req = create_login_request(
        db,
        process="signup_client",
        register_fio="Петр Петров",
        register_phone="+79991112233",
        next_url="/",
    )
    ok, msg, out = confirm_login_via_bot(db, req.token, telegram_id=777001, username="petr")
    assert ok, msg
    user = db.get(User, out.user_id)
    assert user is not None
    assert find_consultant_for_user(db, user.id) is None
    assert (user.first_name or "") != "" or (user.last_name or "") != ""
    db.close()


def test_signup_specialist_still_creates_consultant():
    db = _session()
    req = create_login_request(
        db,
        process="signup",
        register_fio="Сидор Сидоров",
        register_phone="+79993334455",
        next_url="/",
    )
    ok, msg, out = confirm_login_via_bot(db, req.token, telegram_id=777002, username="sid")
    assert ok, msg
    consultant = find_consultant_for_user(db, out.user_id)
    assert consultant is not None
    integ = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
    assert integ is not None
    assert integ.telegram_chat_id is None
    db.close()


def test_become_specialist_idempotent():
    db = _session()
    user = User(username="c1", password="x", email="c1@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    c1 = create_consultant_for_user(db, user, fio="А Б", phone="+79990001122", email="c1@t.c")
    c2 = create_consultant_for_user(db, user, fio="А Б", phone="+79990001122", email="c1@t.c")
    assert c1.id == c2.id
    assert db.query(Consultant).filter(Consultant.user_id == user.id).count() == 1
    db.close()
