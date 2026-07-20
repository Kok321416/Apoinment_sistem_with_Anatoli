"""Ensure auth tables exist (telegram login flow)."""
from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import auth as auth_models  # noqa: F401 - register models


def ensure_telegram_login_schema() -> None:
    Base.metadata.create_all(bind=engine, tables=[auth_models.TelegramLoginRequest.__table__])

    inspector = inspect(engine)
    if not inspector.has_table("telegram_login_requests"):
        return

    columns = {col["name"] for col in inspector.get_columns("telegram_login_requests")}
    if "consumed_at" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE telegram_login_requests ADD COLUMN consumed_at DATETIME NULL")
            )


if __name__ == "__main__":
    ensure_telegram_login_schema()
    print("telegram_login_requests schema OK")
