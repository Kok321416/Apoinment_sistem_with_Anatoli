from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif settings.database_url.startswith("mysql"):
    connect_args = {
        "connect_timeout": settings.db_connect_timeout,
        "read_timeout": 30,
        "write_timeout": 30,
    }

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    from app.db_schema import ensure_schema_before_query

    ensure_schema_before_query()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
