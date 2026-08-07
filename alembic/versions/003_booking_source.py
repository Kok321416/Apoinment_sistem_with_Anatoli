"""Alembic: bookings.source for client vs specialist-created bookings."""

from alembic import op
import sqlalchemy as sa

revision = "003_booking_source"
down_revision = "002_async_phase_e_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("bookings")}
    if "source" not in cols:
        op.add_column(
            "bookings",
            sa.Column("source", sa.String(32), nullable=True, server_default="client"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("bookings")}
    if "source" in cols:
        op.drop_column("bookings", "source")
