"""Schema ensure for integration_telegram_audit (prod shared hosting)."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.db_schema import ensure_integration_telegram_audit_schema
from app.models import Category, Consultant, Integration
from app.services.integration_telegram import claim_integration_telegram_chat


def test_ensure_integration_telegram_audit_creates_table():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create only integrations deps — not audit table
    Base.metadata.create_all(
        engine,
        tables=[
            Category.__table__,
            Consultant.__table__,
            Integration.__table__,
        ],
    )
    assert not inspect(engine).has_table("integration_telegram_audit")
    assert ensure_integration_telegram_audit_schema(bind=engine) is True
    assert inspect(engine).has_table("integration_telegram_audit")


def test_claim_succeeds_when_audit_table_created_on_the_fly(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Category.__table__,
            Consultant.__table__,
            Integration.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    cat = Category(name_category="Общая")
    db.add(cat)
    db.flush()
    c = Consultant(
        first_name="A",
        last_name="B",
        email="a@b.c",
        phone="+1",
        category_of_specialist_id=cat.id,
    )
    db.add(c)
    db.flush()
    integ = Integration(consultant_id=c.id)
    db.add(integ)
    db.commit()
    db.refresh(integ)

    # Point ensure at this engine so claim creates audit table here
    monkeypatch.setattr(
        "app.db_schema.engine",
        engine,
    )
    ok, msg = claim_integration_telegram_chat(db, integ, "1178777793", source="bot_connect_spec")
    assert ok, msg
    db.commit()
    db.refresh(integ)
    assert integ.telegram_chat_id == "1178777793"
    assert integ.telegram_connected is True
    count = db.execute(text("SELECT COUNT(*) FROM integration_telegram_audit")).scalar()
    assert count == 1
