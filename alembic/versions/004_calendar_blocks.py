"""Alembic revision: calendar_blocks for specialist events."""

from alembic import op
import sqlalchemy as sa


revision = "004_calendar_blocks"
down_revision = "003_booking_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calendar_id", sa.Integer(), sa.ForeignKey("calendars.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("block_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("auth_user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_calendar_blocks_calendar_id", "calendar_blocks", ["calendar_id"])
    op.create_index("ix_calendar_blocks_block_date", "calendar_blocks", ["block_date"])


def downgrade() -> None:
    op.drop_index("ix_calendar_blocks_block_date", table_name="calendar_blocks")
    op.drop_index("ix_calendar_blocks_calendar_id", table_name="calendar_blocks")
    op.drop_table("calendar_blocks")
