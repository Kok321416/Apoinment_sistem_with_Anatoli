"""Ensure DB schema patches that create_all may miss on existing DBs."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import auth as auth_models  # noqa: F401 - register models
from app.models import diagnostics as diagnostics_models  # noqa: F401 - register models
from app.models import core as core_models  # noqa: F401

logger = logging.getLogger(__name__)

_DIAGNOSTICS_TABLES = (
    diagnostics_models.ClientSpecialistLink.__table__,
    diagnostics_models.DiagnosticInvitation.__table__,
    diagnostics_models.DiagnosticAttempt.__table__,
)

_TELEGRAM_LOGIN_COLUMNS = {
    "telegram_id": "VARCHAR(32) NULL",
    "created_at": "DATETIME NULL",
    "consumed_at": "DATETIME NULL",
    "client_channel": "VARCHAR(20) NULL DEFAULT 'web'",
}

_SCHEMA_PATCHES_ATTEMPTED = False
_SCHEMA_FULL_ATTEMPTED = False
_schema_degraded = False
_schema_issues: list[str] = []

_SERVICE_COLUMNS = (
    "calendar_id",
    "color",
    "icon",
    "sort_order",
    "created_at",
    "updated_at",
)


def get_schema_health() -> dict:
    return {
        "ready": _SCHEMA_PATCHES_ATTEMPTED and not _schema_degraded,
        "degraded": _schema_degraded,
        "issues": list(_schema_issues),
        "patches_applied": _SCHEMA_PATCHES_ATTEMPTED,
        "full_migration_applied": _SCHEMA_FULL_ATTEMPTED,
    }


def _table_exists(table: str) -> bool:
    try:
        return inspect(engine).has_table(table)
    except Exception:
        logger.exception("Could not inspect table %s", table)
        return False


def _column_exists(table: str, column: str) -> bool:
    try:
        inspector = inspect(engine)
        if not inspector.has_table(table):
            return False
        return column in {col["name"] for col in inspector.get_columns(table)}
    except Exception:
        logger.exception("Could not inspect %s.%s", table, column)
        return False


def _ddl(ddl: str) -> str:
    if engine.dialect.name == "mysql":
        return ddl.replace("INTEGER", "INT")
    return ddl


_SCHEMA_LOCK_NAME = "ayc_schema_migration"
_SCHEMA_LOCK_WAIT_SEC = 5


@contextmanager
def _schema_migration_lock(*, wait_seconds: int = _SCHEMA_LOCK_WAIT_SEC):
    """Best-effort lock for concurrent Passenger worker startups. Skip if busy."""
    if engine.dialect.name != "mysql":
        yield True
        return
    conn = engine.connect()
    acquired = False
    try:
        try:
            acquired = (
                conn.execute(
                    text(f"SELECT GET_LOCK('{_SCHEMA_LOCK_NAME}', :wait)"),
                    {"wait": wait_seconds},
                ).scalar()
                == 1
            )
        except Exception:
            logger.exception("Could not acquire schema migration lock")
            acquired = False
        if not acquired:
            logger.warning("Schema migration lock busy; skipping patch in this worker")
        yield acquired
    finally:
        if acquired:
            try:
                conn.execute(text(f"SELECT RELEASE_LOCK('{_SCHEMA_LOCK_NAME}')"))
            except Exception:
                logger.exception("Could not release schema migration lock")
        conn.close()


def _add_column(table: str, column: str, ddl: str) -> None:
    if not _table_exists(table):
        return
    if _column_exists(table, column):
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {_ddl(ddl)}"))
        logger.info("Added column %s.%s", table, column)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "exists" in msg or "already" in msg:
            logger.info("Column %s.%s already present", table, column)
            return
        logger.exception("Could not add %s.%s", table, column)


def _add_unique_index(table: str, index_name: str, column: str) -> None:
    if not _table_exists(table):
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE UNIQUE INDEX {index_name} ON {table} ({column})"))
        logger.info("Created index %s", index_name)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "exists" in msg or "already" in msg:
            return
        logger.exception("Could not create index %s", index_name)


def _add_index(table: str, index_name: str, column: str) -> None:
    """Non-unique index; idempotent. `column` may be comma-separated for composites."""
    if not _table_exists(table):
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE INDEX {index_name} ON {table} ({column})"))
        logger.info("Created index %s", index_name)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "exists" in msg or "already" in msg:
            return
        logger.exception("Could not create index %s", index_name)


def _apply_hot_path_indexes() -> None:
    """Phase E: additive indexes for booking/slots/auth hot paths (idempotent)."""
    # Already in alembic 001; keep here for deploys that only run db_schema patches.
    _add_index("bookings", "ix_bookings_calendar_date_status", "calendar_id, booking_date, status")
    _add_index("time_slots", "ix_time_slots_calendar_dow", "calendar_id, day_of_week, is_available")
    # Phase E expansion
    _add_index("bookings", "ix_bookings_telegram_id", "telegram_id")
    _add_index("bookings", "ix_bookings_status_date", "status, booking_date")
    _add_index("calendars", "ix_calendars_consultant_active", "consultant_id, is_active")
    _add_index("services", "ix_services_consultant_active", "consultant_id, is_active")
    _add_index("services", "ix_services_calendar_id", "calendar_id")
    _add_index("consultants", "ix_consultants_user_id", "user_id")
    _add_index(
        "socialaccount_socialaccount",
        "ix_socialaccount_provider_uid",
        "provider, uid",
    )
    _add_index("socialaccount_socialaccount", "ix_socialaccount_user_id", "user_id")
    _add_index("integrations", "ix_integrations_telegram_chat_id", "telegram_chat_id")
    _add_index(
        "consultant_client_cards",
        "ix_client_cards_consultant_id",
        "consultant_id",
    )


def _refresh_schema_health() -> None:
    global _schema_degraded, _schema_issues
    issues: list[str] = []
    if _table_exists("calendars") and not _column_exists("calendars", "disabled_weekdays"):
        issues.append("calendars.disabled_weekdays missing")
        logger.critical("Schema degraded: calendars.disabled_weekdays is missing")
    if _table_exists("services"):
        for column in _SERVICE_COLUMNS:
            if not _column_exists("services", column):
                issue = f"services.{column} missing"
                issues.append(issue)
                logger.critical("Schema degraded: %s", issue)
    _schema_issues = issues
    _schema_degraded = bool(issues)


def _apply_app_schema_patches() -> None:
    """Column patches required by current ORM models on legacy MySQL tables."""
    try:
        _add_column("consultant_menu_category", "code", "VARCHAR(64) NOT NULL DEFAULT 'general'")
    except Exception:
        logger.exception("consultant_menu_category.code patch failed")

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
        _add_column("calendars", "disabled_weekdays", "VARCHAR(32) NOT NULL DEFAULT ''")
    except Exception:
        logger.exception("calendars.disabled_weekdays patch failed")

    for column, ddl in (
        ("color", "VARCHAR(7) NOT NULL DEFAULT '#7d5cff'"),
        ("icon", "VARCHAR(50) NULL"),
        ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
        ("created_at", "DATETIME NULL"),
        ("updated_at", "DATETIME NULL"),
    ):
        try:
            _add_column("services", column, ddl)
        except Exception:
            logger.exception("services.%s patch failed", column)

    # Dual-role Phase 1: additive only (no UX change)
    try:
        _add_column("bookings", "client_user_id", "INTEGER NULL")
        _add_index("bookings", "ix_bookings_client_user_id", "client_user_id")
    except Exception:
        logger.exception("bookings.client_user_id patch failed")

    # Dual-role Phase 9
    try:
        _add_column("consultant_client_cards", "client_user_id", "INTEGER NULL")
        _add_index("consultant_client_cards", "ix_client_cards_client_user_id", "client_user_id")
    except Exception:
        logger.exception("consultant_client_cards.client_user_id patch failed")

    # Admin A0 / Phase 10
    try:
        _add_column("auth_user", "notify_broadcast", "BOOLEAN NOT NULL DEFAULT 0")
    except Exception:
        logger.exception("auth_user.notify_broadcast patch failed")

    try:
        _add_column("auth_user", "session_version", "INTEGER NOT NULL DEFAULT 0")
    except Exception:
        logger.exception("auth_user.session_version patch failed")

    try:
        _add_column("bookings", "vk_user_id", "BIGINT NULL")
        _add_index("bookings", "ix_bookings_vk_user_id", "vk_user_id")
    except Exception:
        logger.exception("bookings.vk_user_id patch failed")

    try:
        _add_column("bookings", "source", "VARCHAR(32) NULL DEFAULT 'client'")
    except Exception:
        logger.exception("bookings.source patch failed")
    try:
        _add_column("bookings", "cancel_reason", "TEXT NULL")
    except Exception:
        logger.exception("bookings.cancel_reason patch failed")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE bookings SET source = 'client' "
                    "WHERE source IS NULL OR source = ''"
                )
            )
    except Exception:
        logger.exception("bookings.source backfill failed")

    try:
        from app.models import platform as platform_models

        Base.metadata.create_all(
            bind=engine,
            tables=[
                platform_models.AdminAuditLog.__table__,
                platform_models.TelegramBroadcastJob.__table__,
                platform_models.TelegramBroadcastRecipient.__table__,
                platform_models.PlatformErrorLog.__table__,
                platform_models.EmailDeliveryLog.__table__,
                platform_models.PlatformUserActivity.__table__,
                platform_models.SupportTicket.__table__,
                platform_models.SupportTicketMessage.__table__,
                platform_models.AdminRoleAssignment.__table__,
                platform_models.AdminTwoFactor.__table__,
                platform_models.UserTwoFactor.__table__,
                platform_models.BillingPlan.__table__,
                platform_models.UserSubscription.__table__,
            ],
        )
    except Exception:
        logger.exception("platform admin tables create_all failed")

    try:
        ensure_diagnostics_schema()
    except Exception:
        logger.exception("diagnostics tables create_all failed")

    try:
        _apply_hot_path_indexes()
    except Exception:
        logger.exception("hot-path indexes patch failed")

    _refresh_schema_health()


def ensure_app_schema() -> None:
    """Backward-compatible alias used in tests."""
    ensure_schema_patches()


def ensure_schema_patches(*, use_lock: bool = True) -> None:
    """Lightweight idempotent patches. Safe to run once per process on import."""
    global _SCHEMA_PATCHES_ATTEMPTED
    if _SCHEMA_PATCHES_ATTEMPTED:
        return

    def _run() -> None:
        global _SCHEMA_PATCHES_ATTEMPTED
        if _SCHEMA_PATCHES_ATTEMPTED:
            return
        _apply_app_schema_patches()
        _SCHEMA_PATCHES_ATTEMPTED = True

    if not use_lock:
        _run()
        return

    with _schema_migration_lock() as acquired:
        if not acquired:
            _refresh_schema_health()
            return
        _run()


def ensure_telegram_login_schema() -> None:
    try:
        Base.metadata.create_all(bind=engine, tables=[auth_models.TelegramLoginRequest.__table__])
    except Exception:
        logger.exception("telegram_login create_all failed")

    if not _table_exists("telegram_login_requests"):
        return

    for name, ddl in _TELEGRAM_LOGIN_COLUMNS.items():
        try:
            _add_column("telegram_login_requests", name, ddl)
        except Exception:
            logger.exception("telegram_login column %s failed", name)

    try:
        Base.metadata.create_all(bind=engine, tables=[auth_models.TelegramUiPreference.__table__])
    except Exception:
        logger.exception("telegram_ui_preferences create_all failed")

    try:
        Base.metadata.create_all(bind=engine, tables=[auth_models.NativeAuthHandoff.__table__])
    except Exception:
        logger.exception("native_auth_handoffs create_all failed")


def ensure_email_auth_schema() -> None:
    try:
        Base.metadata.create_all(
            bind=engine,
            tables=[
                auth_models.EmailAddress.__table__,
                auth_models.EmailVerificationToken.__table__,
                auth_models.PasswordResetToken.__table__,
            ],
        )
    except Exception:
        logger.exception("email auth schema ensure failed")


def ensure_diagnostics_schema(bind=None) -> bool:
    """Create diagnostics tables if missing. Safe to call repeatedly."""
    bind = bind or engine
    try:
        insp = inspect(bind)
        missing = [t for t in _DIAGNOSTICS_TABLES if not insp.has_table(t.name)]
        if not missing:
            return True
        for table in _DIAGNOSTICS_TABLES:
            if table not in missing:
                continue
            Base.metadata.create_all(bind=bind, tables=[table])
        insp = inspect(bind)
        still_missing = [t.name for t in _DIAGNOSTICS_TABLES if not insp.has_table(t.name)]
        if still_missing:
            logger.error("diagnostics tables still missing: %s", still_missing)
            return False
        logger.info("Created diagnostics tables: %s", [t.name for t in missing])
        return True
    except Exception:
        logger.exception("ensure_diagnostics_schema failed")
        return False


def ensure_all_schema() -> None:
    """Full schema ensure for deploy scripts and dev server startup. Never raises."""
    global _SCHEMA_FULL_ATTEMPTED, _SCHEMA_PATCHES_ATTEMPTED
    if _SCHEMA_FULL_ATTEMPTED:
        return
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logger.exception("create_all failed during ensure_all_schema")
    try:
        ensure_telegram_login_schema()
    except Exception:
        logger.exception("telegram login schema ensure failed")
    try:
        ensure_email_auth_schema()
    except Exception:
        logger.exception("email auth schema ensure failed")
    try:
        ensure_diagnostics_schema()
    except Exception:
        logger.exception("diagnostics schema ensure failed")
    # Deploy/migrate runs in a single process — no MySQL lock (avoids self-deadlock).
    ensure_schema_patches(use_lock=False)
    _refresh_schema_health()
    _SCHEMA_FULL_ATTEMPTED = True


def bootstrap_on_import() -> None:
    """Passenger WSGI may skip FastAPI startup — patch schema when the app module loads."""
    try:
        ensure_schema_patches()
    except Exception:
        logger.exception("schema bootstrap on import failed")


if __name__ == "__main__":
    ensure_all_schema()
    health = get_schema_health()
    print("schema", health)
    if health.get("degraded"):
        raise SystemExit(1)
