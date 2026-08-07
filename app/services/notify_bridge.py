"""Fire-and-forget sync notify bridges so AsyncSession handlers do not block on TG/SMTP/Google."""
from __future__ import annotations

import logging
from datetime import date, time

from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import Booking, Calendar, Consultant
from app.services.telegram import (
    _tg_executor,
    notify_booking_rescheduled,
    notify_booking_status_changed,
    on_booking_created,
    on_booking_updated,
)

logger = logging.getLogger(__name__)


def _load_booking(sdb, booking_id: int) -> Booking | None:
    return (
        sdb.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar)
            .joinedload(Calendar.consultant)
            .joinedload(Consultant.integration),
        )
        .filter(Booking.id == booking_id)
        .first()
    )


def _run_on_booking_created(booking_id: int) -> None:
    sdb = SessionLocal()
    try:
        sb = _load_booking(sdb, booking_id)
        if sb:
            on_booking_created(sdb, sb)
            sdb.commit()
    except Exception:
        logger.exception("notify bridge on_booking_created failed id=%s", booking_id)
        try:
            sdb.rollback()
        except Exception:
            pass
    finally:
        sdb.close()


def _run_status_changed(booking_id: int, old_status: str | None) -> None:
    sdb = SessionLocal()
    try:
        sb = _load_booking(sdb, booking_id)
        if sb:
            notify_booking_status_changed(sdb, sb, old_status)
            sdb.commit()
    except Exception:
        logger.exception("notify bridge status_changed failed id=%s", booking_id)
        try:
            sdb.rollback()
        except Exception:
            pass
    finally:
        sdb.close()


def _run_rescheduled(
    booking_id: int,
    old_date: date,
    old_time: time | None,
    old_end_time: time | None,
) -> None:
    sdb = SessionLocal()
    try:
        sb = _load_booking(sdb, booking_id)
        if not sb:
            return
        on_booking_updated(sdb, sb, created=False)
        try:
            notify_booking_rescheduled(
                sdb,
                sb,
                old_date=old_date,
                old_time=old_time,
                old_end_time=old_end_time,
            )
        except Exception:
            logger.exception("notify_booking_rescheduled failed id=%s", booking_id)
        sdb.commit()
    except Exception:
        logger.exception("notify bridge rescheduled failed id=%s", booking_id)
        try:
            sdb.rollback()
        except Exception:
            pass
    finally:
        sdb.close()


def schedule_on_booking_created(booking_id: int) -> None:
    _tg_executor.submit(_run_on_booking_created, int(booking_id))


def schedule_status_changed(booking_id: int, old_status: str | None) -> None:
    _tg_executor.submit(_run_status_changed, int(booking_id), old_status)


def schedule_rescheduled(
    booking_id: int,
    *,
    old_date: date,
    old_time: time | None,
    old_end_time: time | None = None,
) -> None:
    _tg_executor.submit(_run_rescheduled, int(booking_id), old_date, old_time, old_end_time)
