"""Psychological diagnostics models (history-preserving, specialist-scoped)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ClientSpecialistLink(Base):
    """Client ↔ specialist relation (visit, booking, invite, explicit save)."""

    __tablename__ = "client_specialist_links"
    __table_args__ = (
        UniqueConstraint("client_user_id", "consultant_id", name="uq_client_specialist_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_user_id: Mapped[int] = mapped_column(ForeignKey("auth_user.id"), index=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="visit")  # visit|booking|invite|manual
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    consultant = relationship("Consultant")
    client_user = relationship("User")


class DiagnosticInvitation(Base):
    """Secure personal link from specialist to client diagnostics."""

    __tablename__ = "diagnostic_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"), index=True)
    client_user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_user.id"), nullable=True, index=True)
    client_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("consultant_client_cards.id"), nullable=True, index=True
    )
    test_codes_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list; empty = all available
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_user.id"), nullable=True)

    consultant = relationship("Consultant")
    client_card = relationship("ClientCard")


class DiagnosticAttempt(Base):
    """One completed (or in-progress) test run — never overwritten on retest."""

    __tablename__ = "diagnostic_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_user_id: Mapped[int] = mapped_column(ForeignKey("auth_user.id"), index=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"), index=True)
    client_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("consultant_client_cards.id"), nullable=True, index=True
    )
    invitation_id: Mapped[int | None] = mapped_column(
        ForeignKey("diagnostic_invitations.id"), nullable=True, index=True
    )
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True, index=True)

    test_code: Mapped[str] = mapped_column(String(64), index=True)
    test_version: Mapped[str] = mapped_column(String(32), default="1")
    status: Mapped[str] = mapped_column(String(16), default="in_progress")  # in_progress|completed|abandoned
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    scores_json: Mapped[str] = mapped_column(Text, default="{}")
    scales_json: Mapped[str] = mapped_column(Text, default="[]")
    interpretation_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_text: Mapped[str] = mapped_column(Text, default="")
    flags_json: Mapped[str] = mapped_column(Text, default="[]")  # attention / crisis flags
    source: Mapped[str] = mapped_column(String(32), default="cabinet")  # cabinet|invite|post_booking

    consultant = relationship("Consultant")
    client_card = relationship("ClientCard")
    invitation = relationship("DiagnosticInvitation")
