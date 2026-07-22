"""Phase 8 Mini App hub: initData auth + /tg/?mode=."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_db
from app.models import Category, Consultant, SocialAccount, User
from app.services.telegram_webapp_auth import find_or_create_user_from_webapp, validate_webapp_init_data


def _sign_init_data(bot_token: str, fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    pairs = dict(fields)
    pairs["hash"] = digest
    return urlencode(pairs)


def test_validate_webapp_init_data_ok_and_bad():
    token = "123456:ABC-DEF"
    user = {"id": 777001, "first_name": "Ada", "username": "ada"}
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user, separators=(",", ":")),
    }
    init_data = _sign_init_data(token, fields)
    parsed = validate_webapp_init_data(init_data, bot_token=token)
    assert parsed is not None
    assert parsed["user"]["id"] == 777001

    bad = init_data[:-4] + "dead"
    assert validate_webapp_init_data(bad, bot_token=token) is None


def test_find_or_create_user_from_webapp_creates_client_only():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = find_or_create_user_from_webapp(
        db,
        {"id": 555200, "first_name": "Bob", "username": "bob"},
    )
    assert user is not None
    assert user.username == "telegram_555200"
    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.provider == "telegram", SocialAccount.uid == "555200")
        .first()
    )
    assert sa is not None
    assert db.query(Consultant).filter(Consultant.user_id == user.id).first() is None

    again = find_or_create_user_from_webapp(db, {"id": 555200, "first_name": "Bob"})
    assert again.id == user.id
    db.close()


def test_webapp_auth_api_sets_session_and_mode(monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.main import app

    token = "999888:TEST-TOKEN"
    monkeypatch.setattr(
        "app.services.telegram_webapp_auth.get_settings",
        lambda: SimpleNamespace(telegram_bot_token=token),
    )

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
        fields = {
            "auth_date": str(int(time.time())),
            "user": json.dumps(
                {"id": 424242, "first_name": "Cara", "username": "cara"},
                separators=(",", ":"),
            ),
        }
        init_data = _sign_init_data(token, fields)
        r = client.post(
            "/api/telegram/webapp-auth",
            json={"init_data": init_data, "mode": "client"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        assert body.get("has_consultant") is False

        db = Session()
        cat = Category(name_category="Общая")
        db.add(cat)
        db.flush()
        user = db.query(User).filter(User.username == "telegram_424242").one()
        db.add(
            Consultant(
                first_name="C",
                last_name="A",
                email=user.email,
                phone="+7000",
                category_of_specialist_id=cat.id,
                user_id=user.id,
            )
        )
        db.commit()
        db.close()

        r2 = client.post(
            "/api/telegram/webapp-auth",
            json={"init_data": init_data, "mode": "specialist"},
        )
        assert r2.status_code == 200
        assert r2.json().get("has_consultant") is True

        hub = client.get("/tg/")
        assert hub.status_code == 200
        assert "Режим: специалист" in hub.text
        assert "Кабинет специалиста" in hub.text
    finally:
        app.dependency_overrides.clear()
