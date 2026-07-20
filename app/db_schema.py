"""Ensure auth tables exist (telegram login flow)."""
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


if __name__ == "__main__":
    ensure_telegram_login_schema()
    print("telegram_login_requests schema OK")
