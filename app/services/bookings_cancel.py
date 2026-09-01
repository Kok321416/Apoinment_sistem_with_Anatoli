"""Specialist-initiated booking cancellation with a client-visible reason."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, Integration

MAX_CANCEL_REASON_LEN = 500
MIN_CANCEL_REASON_LEN = 3

CANCELLABLE_STATUSES = frozenset({"pending", "confirmed"})


def normalize_cancel_reason(raw: str | None) -> tuple[str | None, str | None]:
    text = (raw or "").strip()
    if len(text) < MIN_CANCEL_REASON_LEN:
        return None, f"Укажите причину отмены (минимум {MIN_CANCEL_REASON_LEN} символа)"
    if len(text) > MAX_CANCEL_REASON_LEN:
        return None, f"Причина слишком длинная (максимум {MAX_CANCEL_REASON_LEN} символов)"
    return text, None


def can_cancel_booking_status(status: str | None) -> bool:
    return (status or "") in CANCELLABLE_STATUSES


async def specialist_cancel_booking_async(
    db: AsyncSession,
    *,
    consultant_id: int,
    booking_id: int,
    reason: str,
) -> tuple[bool, str, Booking | None]:
    """Cancel a booking owned by consultant_id. Returns (ok, error_or_message, booking)."""
    norm, err = normalize_cancel_reason(reason)
    if err:
        return False, err, None

    booking = (
        await db.execute(
            select(Booking)
            .join(Calendar, Booking.calendar_id == Calendar.id)
            .where(Booking.id == int(booking_id), Calendar.consultant_id == int(consultant_id))
        )
    ).scalar_one_or_none()
    if not booking:
        return False, "booking not found", None
    if booking.status == "cancelled":
        return True, "Запись уже отменена", booking
    if not can_cancel_booking_status(booking.status):
        return False, "booking not cancellable", None

    old_status = booking.status
    booking.status = "cancelled"
    booking.cancel_reason = norm
    await db.commit()
    from app.services.notify_bridge import schedule_status_changed

    schedule_status_changed(booking.id, old_status)
    return True, "Запись отменена", booking


def specialist_cancel_booking_sync(
    db: Session,
    *,
    consultant_id: int,
    booking_id: int,
    reason: str,
) -> tuple[bool, str, Booking | None]:
    norm, err = normalize_cancel_reason(reason)
    if err:
        return False, err, None

    booking = (
        db.query(Booking)
        .join(Calendar, Booking.calendar_id == Calendar.id)
        .filter(Booking.id == int(booking_id), Calendar.consultant_id == int(consultant_id))
        .first()
    )
    if not booking:
        return False, "booking not found", None
    if booking.status == "cancelled":
        return True, "Запись уже отменена", booking
    if not can_cancel_booking_status(booking.status):
        return False, "booking not cancellable", None

    old_status = booking.status
    booking.status = "cancelled"
    booking.cancel_reason = norm
    db.commit()
    from app.services.notify_bridge import schedule_status_changed

    schedule_status_changed(booking.id, old_status)
    return True, "Запись отменена", booking


async def resolve_consultant_id_by_telegram_chat(db: AsyncSession, chat_id) -> int | None:
    integration = (
        await db.execute(
            select(Integration).where(Integration.telegram_chat_id == str(chat_id).strip())
        )
    ).scalar_one_or_none()
    if not integration:
        return None
    return int(integration.consultant_id)
