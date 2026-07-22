"""Phase 4: SocialAccount login must not write Integration.telegram_chat_id."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import Category, Consultant, Integration, SocialAccount, User
from app.services.integration_telegram import claim_integration_telegram_chat
from app.services.telegram_auth import confirm_login_via_bot, create_login_request


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_connect_does_not_set_integration_chat():
    db = _session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    user = User(username="spec", password="x", email="s@t.c", date_joined=datetime.now())
    db.add(user)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="s@t.c",
        phone="+7999",
        category_of_specialist_id=cat.id,
        user_id=user.id,
    )
    db.add(c)
    db.flush()
    integ = Integration(consultant_id=c.id)
    db.add(integ)
    db.commit()

    req = create_login_request(db, process="connect", connect_user_id=user.id, next_url="/")
    ok, msg, out = confirm_login_via_bot(db, req.token, telegram_id=424242, username="nick")
    assert ok, msg
    db.refresh(integ)
    social = db.query(SocialAccount).filter(SocialAccount.uid == "424242").first()
    assert social is not None
    assert social.user_id == user.id
    assert integ.telegram_chat_id is None
    assert integ.telegram_connected is False
    db.refresh(c)
    assert c.telegram_nickname == "nick"
    db.close()


def test_signup_creates_integration_stub_without_chat():
    db = _session()
    req = create_login_request(
        db,
        process="signup",
        register_fio="Иван Иванов",
        register_phone="+79991234567",
        next_url="/",
    )
    ok, msg, out = confirm_login_via_bot(db, req.token, telegram_id=555001, username="ivan")
    assert ok, msg
    user = db.get(User, out.user_id)
    assert user is not None
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
    assert consultant is not None
    integ = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
    assert integ is not None
    assert integ.telegram_chat_id is None
    assert integ.telegram_connected is False
    db.close()


def test_claim_integration_rejects_shared_chat():
    db = _session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c1 = Consultant(
        first_name="A",
        last_name="B",
        email="a@t.c",
        phone="+7111",
        category_of_specialist_id=cat.id,
    )
    c2 = Consultant(
        first_name="C",
        last_name="D",
        email="b@t.c",
        phone="+7222",
        category_of_specialist_id=cat.id,
    )
    db.add_all([c1, c2])
    db.flush()
    i1 = Integration(consultant_id=c1.id, telegram_chat_id="900", telegram_connected=True, telegram_enabled=True)
    i2 = Integration(consultant_id=c2.id)
    db.add_all([i1, i2])
    db.commit()

    ok, err = claim_integration_telegram_chat(db, i2, "900")
    assert ok is False
    assert "другому" in err.lower() or "уже" in err.lower()

    ok2, _ = claim_integration_telegram_chat(db, i2, "901")
    assert ok2 is True
    assert i2.telegram_chat_id == "901"
    db.close()
