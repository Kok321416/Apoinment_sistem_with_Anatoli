"""Engines and session factories.

How to get an async session:

* inside a request handler — ``db: AsyncSession = Depends(get_async_db)``
* outside a request (SSE, background threads, CLI) — ``async with async_session() as db``
* in tests and scripts — ``configure_async_sessionmaker(factory)`` / ``reset_async_sessionmaker()``

The engine and the session factory are module-private on purpose: the lazy bootstrap, the
override seam and session cleanup all live behind the functions above, so renaming an internal
never breaks callers.
"""

import threading
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
_is_mysql = settings.database_url.startswith("mysql")

connect_args: dict = {}
if _is_sqlite:
    connect_args = {"check_same_thread": False}
elif _is_mysql:
    connect_args = {
        "connect_timeout": settings.db_connect_timeout,
        "read_timeout": 30,
        "write_timeout": 30,
    }

_engine_kwargs: dict = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
if not _is_sqlite:
    _engine_kwargs["pool_size"] = settings.db_pool_size
    _engine_kwargs["max_overflow"] = settings.db_max_overflow

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

_async_engine = None
_async_sessionmaker = None
_async_init_lock = threading.Lock()


def _build_async_sessionmaker():
    """Async engine is built lazily so sync-only deploys can import app without async deps."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    async_connect_args: dict = {}
    if settings.async_database_url.startswith("sqlite"):
        async_connect_args = {"check_same_thread": False}
    async_kwargs: dict = {
        "connect_args": async_connect_args,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    if not settings.async_database_url.startswith("sqlite"):
        async_kwargs["pool_size"] = settings.db_pool_size
        async_kwargs["max_overflow"] = settings.db_max_overflow
    new_engine = create_async_engine(settings.async_database_url, **async_kwargs)
    factory = async_sessionmaker(
        bind=new_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return new_engine, factory


def get_async_sessionmaker():
    """Async session factory for the configured database."""
    global _async_engine, _async_sessionmaker

    if _async_sessionmaker is not None:
        return _async_sessionmaker
    with _async_init_lock:
        if _async_sessionmaker is None:
            _async_engine, _async_sessionmaker = _build_async_sessionmaker()
        return _async_sessionmaker


def get_async_engine():
    """Async engine behind :func:`get_async_sessionmaker` (built on first use)."""
    get_async_sessionmaker()
    return _async_engine


def configure_async_sessionmaker(session_factory, *, async_engine=None) -> None:
    """Point async sessions at a different database — the supported seam for tests and scripts."""
    global _async_engine, _async_sessionmaker

    with _async_init_lock:
        _async_engine = async_engine
        _async_sessionmaker = session_factory


def reset_async_sessionmaker() -> None:
    """Forget the current factory; the next session rebuilds it from settings."""
    configure_async_sessionmaker(None)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """Sync session (legacy). Prefer get_async_db for new / hot-path code."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def async_session() -> AsyncGenerator:
    """Async session for code that has no request-scoped dependency to lean on."""
    factory = get_async_sessionmaker()
    async with factory() as session:
        yield session


async def get_async_db() -> AsyncGenerator:
    async with async_session() as session:
        yield session
