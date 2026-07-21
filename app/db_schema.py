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

_schema_ready = False
_schema_degraded = False
_schema_issues: list[str] = []


def get_schema_health() -> dict:
    return {
        "ready": _schema_ready,
        "degraded": _schema_degraded,
        "issues": list(_schema_issues),
    }


def _column_exists(table: str, column: str) -> bool:
    try:
        inspector = inspect(engine)
        if not inspector.has_table(table):
            return False
        return column in {col["name"] for col in inspector.get_columns(table)}
    except Exception:
        logger.exception("Could not inspect %s.%s", table, column)
        return False


def _add_column(table: str, column: str, ddl: str) -> None:
    if _column_exists(table, column):
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        logger.info("Added column %s.%s", table, column)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "exists" in msg or "already" in msg:
            logger.info("Column %s.%s already present", table, column)
            return
        logger.exception("Could not add %s.%s", table, column)


def _add_unique_index(table: str, index_name: str, column: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE UNIQUE INDEX {index_name} ON {table} ({column})"))
        logger.info("Created index %s", index_name)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "exists" in msg or "already" in msg:
            return
        logger.exception("Could not create index %s", index_name)


def ensure_telegram_login_schema() -> None:
    Base.metadata.create_all(bind=engine, tables=[auth_models.TelegramLoginRequest.__table__])

    inspector = inspect(engine)
    if not inspector.has_table("telegram_login_requests"):
        return

    for name, ddl in _TELEGRAM_LOGIN_COLUMNS.items():
        try:
            _add_column("telegram_login_requests", name, ddl)
        except Exception:
            logger.exception("telegram_login column %s failed", name)


def _refresh_schema_health() -> None:
    global _schema_degraded, _schema_issues
    issues: list[str] = []
    # ORM maps Service.calendar_id — missing column breaks services/booking.
    if not _column_exists("services", "calendar_id"):
        issues.append("services.calendar_id missing")
        logger.critical("Schema degraded: services.calendar_id is missing")
    _schema_issues = issues
    _schema_degraded = bool(issues)


def ensure_email_auth_schema() -> None:
    """Email verification tables may be missing on older production DBs."""
    try:
        Base.metadata.create_all(
            bind=engine,
            tables=[
                auth_models.EmailAddress.__table__,
                auth_models.EmailVerificationToken.__table__,
            ],
        )
    except Exception:
        logger.exception("email auth schema ensure failed")


def ensure_app_schema() -> None:
    """Idempotent patches required by the current app code. Never raises."""
    try:
        _add_column("consultants", "public_slug", "VARCHAR(64) NULL")
        _add_unique_index("consultants", "ix_consultants_public_slug", "public_slug")
    except Exception:
        logger.exception("consultants.public_slug patch failed")

    try:
        _add_column("services", "calendar_id", "INTEGER NULL")
    except Exception:
        logger.exception("services.calendar_id patch failed")

    try:
        _add_column("calendars", "disabled_weekdays", "VARCHAR(32) DEFAULT ''")
    except Exception:
        logger.exception("calendars.disabled_weekdays patch failed")

    try:
        _add_column("services", "color", "VARCHAR(7) DEFAULT '#7d5cff'")
    except Exception:
        logger.exception("services.color patch failed")

    try:
        _add_column("services", "icon", "VARCHAR(50) NULL")
    except Exception:
        logger.exception("services.icon patch failed")

    try:
        _add_column("services", "sort_order", "INTEGER DEFAULT 0")
    except Exception:
        logger.exception("services.sort_order patch failed")

    _refresh_schema_health()


def ensure_all_schema() -> None:
    global _schema_ready
    try:
        ensure_telegram_login_schema()
    except Exception:
        logger.exception("telegram login schema ensure failed")
    try:
        ensure_email_auth_schema()
    except Exception:
        logger.exception("email auth schema ensure failed")
    ensure_app_schema()
    _schema_ready = True


def ensure_schema_before_query() -> None:
    """Best-effort runtime recovery if startup patch did not run."""
    global _schema_ready
    if _schema_ready:
        return
    try:
        ensure_app_schema()
        _schema_ready = True
    except Exception:
        logger.exception("Runtime schema ensure failed")
        _schema_ready = True


if __name__ == "__main__":
    ensure_all_schema()
    print("schema OK", get_schema_health())
