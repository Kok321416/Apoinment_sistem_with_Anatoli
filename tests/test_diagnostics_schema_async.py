"""Regression: diagnostics schema ensure must not call inspect() on async connections."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.services.diagnostics_service import ensure_diagnostics_tables


@pytest.mark.asyncio
async def test_ensure_diagnostics_tables_async_path_never_inspects_async_bind():
    """inspect(has_table) on asyncmy connection caused MissingGreenlet in production."""
    from app.services.diagnostics_service import reset_diagnostics_ddl_ready_for_tests

    reset_diagnostics_ddl_ready_for_tests()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in ("diagnostic_attempts", "diagnostic_invitations", "client_specialist_links"):
            try:
                await conn.execute(__import__("sqlalchemy").text(f"DROP TABLE IF EXISTS {table}"))
            except Exception:
                pass

    inspect_calls: list[object] = []
    real_inspect = __import__("sqlalchemy", fromlist=["inspect"]).inspect

    def _tracking_inspect(bind):
        inspect_calls.append(bind)
        return real_inspect(bind)

    with patch("app.db_schema.ensure_diagnostics_schema", return_value=False):
        with patch("app.db_schema.inspect", side_effect=_tracking_inspect):
            async with session_factory() as db:
                ok = await ensure_diagnostics_tables(db)
                assert ok is True

    async with session_factory() as db:
        from sqlalchemy import text

        row = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        names = {r[0] for r in row.fetchall()}
        assert "diagnostic_attempts" in names

    await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_diagnostics_tables_concurrent_calls_are_idempotent():
    """Repeated ensure_diagnostics_tables must be idempotent and create missing tables."""
    from app.services.diagnostics_service import reset_diagnostics_ddl_ready_for_tests

    reset_diagnostics_ddl_ready_for_tests()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in ("diagnostic_attempts", "diagnostic_invitations", "client_specialist_links"):
            try:
                await conn.execute(__import__("sqlalchemy").text(f"DROP TABLE IF EXISTS {table}"))
            except Exception:
                pass

    with patch("app.db_schema.ensure_diagnostics_schema", return_value=False):
        for _ in range(8):
            async with session_factory() as db:
                assert await ensure_diagnostics_tables(db) is True

    async with session_factory() as db:
        from sqlalchemy import text

        row = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        names = {r[0] for r in row.fetchall()}
        assert "diagnostic_attempts" in names
        assert "diagnostic_invitations" in names
        assert "client_specialist_links" in names

    await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_diagnostics_tables_skips_ddl_when_already_ready():
    from app.services import diagnostics_service as ds

    ds.reset_diagnostics_ddl_ready_for_tests()
    ds._mark_diagnostics_ddl_ready()

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch.object(ds, "_ensure_diagnostics_tables_on_session") as async_ddl:
        with patch("app.db_schema.ensure_diagnostics_schema") as sync_ensure:
            async with session_factory() as db:
                ok = await ds.ensure_diagnostics_tables(db)
            assert ok is True
            sync_ensure.assert_not_called()
            async_ddl.assert_not_called()

    ds.reset_diagnostics_ddl_ready_for_tests()
    await engine.dispose()
