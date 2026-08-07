from collections.abc import AsyncGenerator, Generator

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
_AsyncSessionLocal = None


def _ensure_async_engine():
    """Lazy async engine so sync-only deploys can import app before async deps are installed."""
    global _async_engine, _AsyncSessionLocal
    if _AsyncSessionLocal is not None:
        return _AsyncSessionLocal
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
    _async_engine = create_async_engine(settings.async_database_url, **async_kwargs)
    _AsyncSessionLocal = async_sessionmaker(
        bind=_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return _AsyncSessionLocal


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """Sync session (legacy). Prefer get_async_db for new / hot-path code."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator:
    factory = _ensure_async_engine()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
