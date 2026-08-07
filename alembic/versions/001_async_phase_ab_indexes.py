"""baseline + hot-path indexes for bookings/slots

Revision ID: 001_async_phase_ab
Revises:
Create Date: 2026-08-07

Baseline: existing schema is managed by app/db_schema.py create_all + patches.
This revision only adds performance indexes (MySQL 8 online where possible).
SQLite: IF NOT EXISTS style via batch; ignore if unsupported.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001_async_phase_ab"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    def _has_index(table: str, name: str) -> bool:
        try:
            return any(ix.get("name") == name for ix in inspector.get_indexes(table))
        except Exception:
            return False

    if inspector.has_table("bookings") and not _has_index("bookings", "ix_bookings_calendar_date_status"):
        if dialect == "mysql":
            op.execute(
                "CREATE INDEX ix_bookings_calendar_date_status "
                "ON bookings (calendar_id, booking_date, status)"
            )
        else:
            op.create_index(
                "ix_bookings_calendar_date_status",
                "bookings",
                ["calendar_id", "booking_date", "status"],
            )

    if inspector.has_table("time_slots") and not _has_index("time_slots", "ix_time_slots_calendar_dow"):
        if dialect == "mysql":
            op.execute(
                "CREATE INDEX ix_time_slots_calendar_dow "
                "ON time_slots (calendar_id, day_of_week, is_available)"
            )
        else:
            op.create_index(
                "ix_time_slots_calendar_dow",
                "time_slots",
                ["calendar_id", "day_of_week", "is_available"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _has_index(table: str, name: str) -> bool:
        try:
            return any(ix.get("name") == name for ix in inspector.get_indexes(table))
        except Exception:
            return False

    if inspector.has_table("time_slots") and _has_index("time_slots", "ix_time_slots_calendar_dow"):
        op.drop_index("ix_time_slots_calendar_dow", table_name="time_slots")
    if inspector.has_table("bookings") and _has_index("bookings", "ix_bookings_calendar_date_status"):
        op.drop_index("ix_bookings_calendar_date_status", table_name="bookings")
