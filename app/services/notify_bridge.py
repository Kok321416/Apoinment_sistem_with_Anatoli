"""Fire-and-forget sync notify bridges so AsyncSession handlers do not block on TG/SMTP/Google.

Create / cancel / reschedule support blocking wait + durable outbox retry.
"""
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


def _enqueue(kind_fn, *args, **kwargs) -> int | None:
    sdb = SessionLocal()
    try:
        oid = kind_fn(sdb, *args, **kwargs)
        sdb.commit()
        return oid
    except Exception:
        logger.exception("outbox enqueue failed")
        try:
            sdb.rollback()
        except Exception:
            pass
        return None
    finally:
        sdb.close()


def _run_on_booking_created(booking_id: int, *, outbox_id: int | None = None) -> None:
    sdb = SessionLocal()
    try:
        sb = _load_booking(sdb, booking_id)
        if sb:
            on_booking_created(sdb, sb)
            if outbox_id:
                from app.services.notify_outbox import mark_outbox_done

                mark_outbox_done(sdb, outbox_id)
            sdb.commit()
    except Exception:
        logger.exception("notify bridge on_booking_created failed id=%s", booking_id)
        try:
            sdb.rollback()
        except Exception:
            pass
    finally:
        sdb.close()


def _run_status_changed(booking_id: int, old_status: str | None, *, outbox_id: int | None = None) -> None:
    sdb = SessionLocal()
    try:
        sb = _load_booking(sdb, booking_id)
        if sb:
            notify_booking_status_changed(sdb, sb, old_status)
            if outbox_id:
                from app.services.notify_outbox import mark_outbox_done

                mark_outbox_done(sdb, outbox_id)
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
    *,
    outbox_id: int | None = None,
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
        if outbox_id:
            from app.services.notify_outbox import mark_outbox_done

            mark_outbox_done(sdb, outbox_id)
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
    from app.services.notify_outbox import enqueue_booking_created

    outbox_id = _enqueue(enqueue_booking_created, int(booking_id))
    _tg_executor.submit(_run_on_booking_created, int(booking_id), outbox_id=outbox_id)


def run_on_booking_created_blocking(booking_id: int, *, timeout: float = 15.0) -> None:
    """Run create-notify and wait so Passenger/WSGI does not kill the send mid-flight."""
    from app.services.notify_outbox import enqueue_booking_created

    outbox_id = _enqueue(enqueue_booking_created, int(booking_id))
    fut = _tg_executor.submit(_run_on_booking_created, int(booking_id), outbox_id=outbox_id)
    try:
        fut.result(timeout=timeout)
    except Exception:
        logger.exception(
            "notify bridge on_booking_created wait failed id=%s", booking_id
        )


def schedule_status_changed(booking_id: int, old_status: str | None) -> None:
    from app.services.notify_outbox import enqueue_status_changed

    outbox_id = _enqueue(enqueue_status_changed, int(booking_id), old_status)
    _tg_executor.submit(_run_status_changed, int(booking_id), old_status, outbox_id=outbox_id)


def run_status_changed_blocking(
    booking_id: int, old_status: str | None, *, timeout: float = 20.0
) -> None:
    """Cancel/status notify with wait — same reliability class as create-notify."""
    from app.services.notify_outbox import enqueue_status_changed

    outbox_id = _enqueue(enqueue_status_changed, int(booking_id), old_status)
    fut = _tg_executor.submit(
        _run_status_changed, int(booking_id), old_status, outbox_id=outbox_id
    )
    try:
        fut.result(timeout=timeout)
    except Exception:
        logger.exception(
            "notify bridge status_changed wait failed id=%s", booking_id
        )


def schedule_rescheduled(
    booking_id: int,
    *,
    old_date: date,
    old_time: time | None,
    old_end_time: time | None = None,
) -> None:
    from app.services.notify_outbox import enqueue_rescheduled

    outbox_id = _enqueue(
        enqueue_rescheduled,
        int(booking_id),
        old_date=old_date,
        old_time=old_time,
        old_end_time=old_end_time,
    )
    _tg_executor.submit(
        _run_rescheduled,
        int(booking_id),
        old_date,
        old_time,
        old_end_time,
        outbox_id=outbox_id,
    )


def run_rescheduled_blocking(
    booking_id: int,
    *,
    old_date: date,
    old_time: time | None,
    old_end_time: time | None = None,
    timeout: float = 20.0,
) -> None:
    from app.services.notify_outbox import enqueue_rescheduled

    outbox_id = _enqueue(
        enqueue_rescheduled,
        int(booking_id),
        old_date=old_date,
        old_time=old_time,
        old_end_time=old_end_time,
    )
    fut = _tg_executor.submit(
        _run_rescheduled,
        int(booking_id),
        old_date,
        old_time,
        old_end_time,
        outbox_id=outbox_id,
    )
    try:
        fut.result(timeout=timeout)
    except Exception:
        logger.exception("notify bridge rescheduled wait failed id=%s", booking_id)
