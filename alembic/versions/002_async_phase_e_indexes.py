"""Phase E: additional hot-path indexes (bookings, calendars, social, services).

Revision ID: 002_async_phase_e
Revises: 001_async_phase_ab
Create Date: 2026-08-07

Idempotent: skips when index already exists. MySQL prefers INPLACE where possible.
Also mirrored in app/db_schema._apply_hot_path_indexes for patch-only deploys.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002_async_phase_e"
down_revision = "001_async_phase_ab"
branch_labels = None
depends_on = None

# (table, index_name, columns)
_INDEXES: list[tuple[str, str, list[str]]] = [
    ("bookings", "ix_bookings_telegram_id", ["telegram_id"]),
    ("bookings", "ix_bookings_status_date", ["status", "booking_date"]),
    ("calendars", "ix_calendars_consultant_active", ["consultant_id", "is_active"]),
    ("services", "ix_services_consultant_active", ["consultant_id", "is_active"]),
    ("services", "ix_services_calendar_id", ["calendar_id"]),
    ("consultants", "ix_consultants_user_id", ["user_id"]),
    ("socialaccount_socialaccount", "ix_socialaccount_provider_uid", ["provider", "uid"]),
    ("socialaccount_socialaccount", "ix_socialaccount_user_id", ["user_id"]),
    ("integrations", "ix_integrations_telegram_chat_id", ["telegram_chat_id"]),
    ("consultant_client_cards", "ix_client_cards_consultant_id", ["consultant_id"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    def _has_index(table: str, name: str) -> bool:
        try:
            return any(ix.get("name") == name for ix in inspector.get_indexes(table))
        except Exception:
            return False

    for table, name, cols in _INDEXES:
        if not inspector.has_table(table) or _has_index(table, name):
            continue
        col_sql = ", ".join(cols)
        if dialect == "mysql":
            op.execute(f"CREATE INDEX {name} ON {table} ({col_sql})")
        else:
            op.create_index(name, table, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _has_index(table: str, name: str) -> bool:
        try:
            return any(ix.get("name") == name for ix in inspector.get_indexes(table))
        except Exception:
            return False

    for table, name, _cols in reversed(_INDEXES):
        if inspector.has_table(table) and _has_index(table, name):
            op.drop_index(name, table_name=table)
