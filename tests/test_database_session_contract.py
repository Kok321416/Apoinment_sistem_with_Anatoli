"""The async session contract: one public API, no reaching into app.database internals.

Callers used to grab `app.database._ensure_async_engine` / `_AsyncSessionLocal` directly, so every
rename of those internals broke unrelated code and test setup with an AttributeError. These tests
pin the public API and fail if a new call site starts poking at the private names again.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.database import (
    async_session,
    configure_async_sessionmaker,
    get_async_db,
    get_async_engine,
    get_async_sessionmaker,
    reset_async_sessionmaker,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_API = (
    "get_async_db",
    "async_session",
    "get_async_sessionmaker",
    "get_async_engine",
    "configure_async_sessionmaker",
    "reset_async_sessionmaker",
)
PRIVATE_NAMES = ("_ensure_async_engine", "_AsyncSessionLocal", "_async_sessionmaker", "_async_engine")
SCANNED_DIRS = ("app", "bot", "tests")


def _private_use_pattern() -> re.Pattern[str]:
    """Match the private names only as standalone identifiers, so get_async_engine is fine."""
    alternatives = "|".join(re.escape(name) for name in PRIVATE_NAMES)
    return re.compile(rf"(?<![A-Za-z0-9_])({alternatives})(?![A-Za-z0-9_])")


def _scanned_files():
    own_paths = {Path(database_module.__file__).resolve(), Path(__file__).resolve()}
    for folder in SCANNED_DIRS:
        for path in sorted((REPO_ROOT / folder).rglob("*.py")):
            if path.resolve() not in own_paths:
                yield path


def test_public_async_session_api_is_exported():
    for name in PUBLIC_API:
        assert callable(getattr(database_module, name, None)), f"app.database.{name} must stay public"


def test_no_module_reaches_into_database_internals():
    pattern = _private_use_pattern()
    offenders = []
    for path in _scanned_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{line} -> {match.group(1)}")
    assert not offenders, (
        "app.database internals are private. Use async_session() outside requests, "
        "Depends(get_async_db) inside them, configure_async_sessionmaker() in tests:\n  "
        + "\n  ".join(offenders)
    )


@pytest.fixture()
def tracked_sqlite_sessions():
    """Configure sessions onto in-memory SQLite and record every session handed out."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    base_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    handed_out: list[AsyncSession] = []

    def factory(*args, **kwargs):
        session = base_factory(*args, **kwargs)
        handed_out.append(session)
        return session

    configure_async_sessionmaker(factory, async_engine=engine)
    try:
        yield factory, engine, handed_out
    finally:
        reset_async_sessionmaker()


async def test_configure_redirects_sessions_and_engine(tracked_sqlite_sessions):
    factory, engine, handed_out = tracked_sqlite_sessions

    assert get_async_sessionmaker() is factory
    assert get_async_engine() is engine

    async with async_session() as db:
        assert (await db.execute(text("select 1"))).scalar_one() == 1
    assert handed_out == [db]
    assert not db.in_transaction()


async def test_get_async_db_uses_configured_factory(tracked_sqlite_sessions):
    _factory, _engine, handed_out = tracked_sqlite_sessions

    generator = get_async_db()
    db = await anext(generator)
    try:
        assert handed_out == [db]
        assert (await db.execute(text("select 2"))).scalar_one() == 2
    finally:
        await generator.aclose()
    assert not db.in_transaction()


async def test_async_session_closes_when_body_raises(tracked_sqlite_sessions):
    _factory, _engine, handed_out = tracked_sqlite_sessions

    with pytest.raises(RuntimeError):
        async with async_session() as db:
            await db.execute(text("select 3"))
            raise RuntimeError("boom")

    assert handed_out == [db]
    assert not db.in_transaction()


async def test_reset_drops_the_override(tracked_sqlite_sessions):
    factory, _engine, _handed_out = tracked_sqlite_sessions

    reset_async_sessionmaker()
    replacement = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    configure_async_sessionmaker(replacement)

    assert get_async_sessionmaker() is replacement
    assert get_async_sessionmaker() is not factory
