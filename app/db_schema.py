"""Ensure DB schema patches that create_all may miss on existing DBs."""
import logging

from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import auth as auth_models  # noqa: F401 - register models

logger = logging.getLogger(__name__)

_TELEGRAM_LOGIN_COLUMNS = {
    "telegram_id": "VARCHAR(32) NULL",
    "created_at": "DATETIME NULL",
    "consumed_at": "DATETIME NULL",
}


def ensure_telegram_login_schema() -> None:
    Base.metadata.create_all(bind=engine, tables=[auth_models.TelegramLoginRequest.__table__])

    inspector = inspect(engine)
    if not inspector.has_table("telegram_login_requests"):
        return

    columns = {col["name"] for col in inspector.get_columns("telegram_login_requests")}
    for name, ddl in _TELEGRAM_LOGIN_COLUMNS.items():
        if name in columns:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE telegram_login_requests ADD COLUMN {name} {ddl}")
                )
            logger.info("Added column telegram_login_requests.%s", name)
        except Exception:
            logger.exception("Could not add %s to telegram_login_requests", name)


def ensure_app_schema() -> None:
    inspector = inspect(engine)
    if inspector.has_table("consultants"):
        columns = {col["name"] for col in inspector.get_columns("consultants")}
        if "public_slug" not in columns:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE consultants ADD COLUMN public_slug VARCHAR(64) NULL"))
                logger.info("Added column consultants.public_slug")
            except Exception:
                logger.exception("Could not add consultants.public_slug")
            try:
                with engine.begin() as conn:
                    conn.execute(text("CREATE UNIQUE INDEX ix_consultants_public_slug ON consultants (public_slug)"))
            except Exception:
                logger.exception("Could not index consultants.public_slug")

    if inspector.has_table("services"):
        columns = {col["name"] for col in inspector.get_columns("services")}
        if "calendar_id" not in columns:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE services ADD COLUMN calendar_id INTEGER NULL"))
                logger.info("Added column services.calendar_id")
            except Exception:
                logger.exception("Could not add services.calendar_id")


def ensure_all_schema() -> None:
    ensure_telegram_login_schema()
    ensure_app_schema()


if __name__ == "__main__":
    ensure_all_schema()
    print("schema OK")
