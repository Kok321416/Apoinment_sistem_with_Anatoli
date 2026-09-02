"""Client contact lookup for public welcome autofill."""
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.passwords import hash_password
from app.database import Base
from app.models import Category, ClientCard, Consultant, User
from app.services.client_auth import lookup_returning_client_async


@pytest.fixture()
async def lookup_db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        cat = Category(name_category="Общая")
        db.add(cat)
        await db.flush()
        consultant = Consultant(
            first_name="Анна",
            last_name="Психолог",
            email="a@test.com",
            phone="+79990001122",
            category_of_specialist_id=cat.id,
            user_id=None,
        )
        db.add(consultant)
        await db.flush()
        client = User(
            username="+79991234567",
            email="",
            password=hash_password("x"),
            first_name="Иван",
            last_name="Петров",
            is_active=True,
            date_joined=datetime.utcnow(),
        )
        db.add(client)
        await db.flush()
        db.add(
            ClientCard(
                consultant_id=consultant.id,
                client_user_id=client.id,
                name="Иван Петров",
                phone="+79991234567",
                telegram="ivan_petrov",
            )
        )
        await db.commit()
        yield db, consultant.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_lookup_by_phone_from_user(lookup_db):
    db, consultant_id = lookup_db
    result = await lookup_returning_client_async(db, phone="+7 (999) 123-45-67", consultant_id=consultant_id)
    assert result
    assert result["found"] is True
    assert "Иван" in result["name"]
    assert result["phone"] == "+79991234567"


@pytest.mark.asyncio
async def test_lookup_by_telegram_from_card(lookup_db):
    db, consultant_id = lookup_db
    result = await lookup_returning_client_async(db, telegram="@ivan_petrov", consultant_id=consultant_id)
    assert result
    assert result["found"] is True
    assert result["telegram"] == "ivan_petrov"
