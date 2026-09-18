"""Durable at-least-once queue for booking notifications."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 12
RETRY_BASE_SEC = 60

KIND_STATUS = "status_changed"
KIND_CREATED = "booking_created"
KIND_RESCHEDULED = "rescheduled"


def _ensure():
    from app.db_schema import ensure_notify_outbox_schema

    return ensure_notify_outbox_schema()


def _bump(db: Session, key: str, by: int = 1) -> None:
    try:
        from app.services.app_counters import increment_counter

        increment_counter(db, key, by=by, commit=False)
    except Exception:
        pass


def _serialize_time(t: time | None) -> str | None:
    if t is None:
        return None
    return t.strftime("%H:%M:%S")


def _parse_time(raw) -> time | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, time):
        return raw
    s = str(raw).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _parse_date(raw) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def enqueue_notify(
    db: Session,
    *,
    kind: str,
    booking_id: int,
    payload: dict | None = None,
) -> int | None:
    """Persist outbox row. Safe if table missing (returns None)."""
    try:
        from app.models import NotifyOutbox

        if not _ensure():
            return None
        row = NotifyOutbox(
            kind=(kind or "")[:32],
            booking_id=int(booking_id),
            payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str),
            attempts=0,
            next_attempt_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        _bump(db, "notify_outbox_enqueued")
        return int(row.id)
    except Exception:
        logger.exception("enqueue_notify failed kind=%s booking_id=%s", kind, booking_id)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def enqueue_status_changed(db: Session, booking_id: int, old_status: str | None) -> int | None:
    return enqueue_notify(
        db,
        kind=KIND_STATUS,
        booking_id=booking_id,
        payload={"old_status": old_status},
    )


def enqueue_booking_created(db: Session, booking_id: int) -> int | None:
    return enqueue_notify(db, kind=KIND_CREATED, booking_id=booking_id, payload={})


def enqueue_rescheduled(
    db: Session,
    booking_id: int,
    *,
    old_date: date,
    old_time: time | None,
    old_end_time: time | None = None,
) -> int | None:
    return enqueue_notify(
        db,
        kind=KIND_RESCHEDULED,
        booking_id=booking_id,
        payload={
            "old_date": old_date.isoformat() if old_date else None,
            "old_time": _serialize_time(old_time),
            "old_end_time": _serialize_time(old_end_time),
        },
    )


def mark_outbox_done(db: Session, outbox_id: int | None) -> None:
    if not outbox_id:
        return
    try:
        from app.models import NotifyOutbox

        row = db.get(NotifyOutbox, int(outbox_id))
        if row and not row.done_at:
            row.done_at = datetime.utcnow()
            row.last_error = None
            db.flush()
            _bump(db, "notify_outbox_done")
    except Exception:
        logger.exception("mark_outbox_done failed id=%s", outbox_id)


def _backoff_seconds(attempts: int) -> int:
    return min(3600, RETRY_BASE_SEC * max(1, 2 ** max(0, attempts - 1)))


def _deliver_row(db: Session, row, payload: dict) -> None:
    from app.services.notify_bridge import _load_booking
    from app.services.telegram import (
        notify_booking_rescheduled,
        notify_booking_status_changed,
        on_booking_created,
        on_booking_updated,
    )

    if not row.booking_id:
        raise ValueError("booking_id required")
    booking = _load_booking(db, int(row.booking_id))
    if not booking:
        row.done_at = datetime.utcnow()
        row.last_error = "booking_missing"
        _bump(db, "notify_outbox_done")
        return

    if row.kind == KIND_STATUS:
        notify_booking_status_changed(db, booking, payload.get("old_status"))
    elif row.kind == KIND_CREATED:
        on_booking_created(db, booking)
    elif row.kind == KIND_RESCHEDULED:
        on_booking_updated(db, booking, created=False)
        notify_booking_rescheduled(
            db,
            booking,
            old_date=_parse_date(payload.get("old_date")) or booking.booking_date,
            old_time=_parse_time(payload.get("old_time")),
            old_end_time=_parse_time(payload.get("old_end_time")),
        )
    else:
        raise ValueError(f"unknown_kind:{row.kind}")

    row.done_at = datetime.utcnow()
    row.last_error = None
    _bump(db, "notify_outbox_done")


def process_notify_outbox(db: Session, *, limit: int = 30) -> dict:
    """Retry pending outbox rows. Called from reminder tick / admin."""
    from app.models import NotifyOutbox

    stats = {"processed": 0, "done": 0, "failed": 0, "skipped": 0}
    if not _ensure():
        return stats
    now = datetime.utcnow()
    rows = (
        db.query(NotifyOutbox)
        .filter(NotifyOutbox.done_at.is_(None), NotifyOutbox.next_attempt_at <= now)
        .order_by(NotifyOutbox.id.asc())
        .limit(limit)
        .all()
    )
    for row in rows:
        stats["processed"] += 1
        if (row.attempts or 0) >= MAX_ATTEMPTS:
            row.next_attempt_at = now + timedelta(days=1)
            row.last_error = (row.last_error or "")[:500] or "max_attempts"
            stats["skipped"] += 1
            continue
        try:
            payload = json.loads(row.payload_json or "{}")
        except Exception:
            payload = {}
        try:
            _deliver_row(db, row, payload if isinstance(payload, dict) else {})
            stats["done"] += 1
        except Exception as e:
            row.attempts = int(row.attempts or 0) + 1
            row.next_attempt_at = now + timedelta(seconds=_backoff_seconds(row.attempts))
            row.last_error = str(e)[:500]
            stats["failed"] += 1
            _bump(db, "notify_outbox_failed")
            _bump(db, "notify_outbox_retried")
            logger.exception("notify_outbox process failed id=%s", row.id)
    try:
        db.commit()
    except Exception:
        logger.exception("notify_outbox commit failed")
        try:
            db.rollback()
        except Exception:
            pass
    return stats


def list_notify_outbox(
    db: Session,
    *,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list:
    from app.models import NotifyOutbox

    if not _ensure():
        return []
    q = db.query(NotifyOutbox).order_by(NotifyOutbox.id.desc())
    if status == "pending":
        q = q.filter(NotifyOutbox.done_at.is_(None))
    elif status == "done":
        q = q.filter(NotifyOutbox.done_at.isnot(None))
    elif status == "failed":
        q = q.filter(NotifyOutbox.done_at.is_(None), NotifyOutbox.attempts > 0)
    if kind:
        q = q.filter(NotifyOutbox.kind == kind)
    return q.limit(limit).all()


async def list_notify_outbox_async(db, *, status: str | None = None, kind: str | None = None, limit: int = 50):
    from sqlalchemy import select
    from app.db_schema import ensure_notify_outbox_schema
    from app.models import NotifyOutbox

    if not ensure_notify_outbox_schema():
        return []
    stmt = select(NotifyOutbox).order_by(NotifyOutbox.id.desc())
    if status == "pending":
        stmt = stmt.where(NotifyOutbox.done_at.is_(None))
    elif status == "done":
        stmt = stmt.where(NotifyOutbox.done_at.isnot(None))
    elif status == "failed":
        stmt = stmt.where(NotifyOutbox.done_at.is_(None), NotifyOutbox.attempts > 0)
    if kind:
        stmt = stmt.where(NotifyOutbox.kind == kind)
    stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


def resend_notify_outbox(db: Session, outbox_id: int) -> tuple[object | None, str | None]:
    """Force immediate retry of one outbox row (admin)."""
    from app.models import NotifyOutbox

    if not _ensure():
        return None, "Таблица notify_outbox недоступна"
    row = db.get(NotifyOutbox, int(outbox_id))
    if not row:
        return None, "Запись не найдена"
    row.done_at = None
    row.next_attempt_at = datetime.utcnow()
    db.flush()
    try:
        payload = json.loads(row.payload_json or "{}")
    except Exception:
        payload = {}
    try:
        _deliver_row(db, row, payload if isinstance(payload, dict) else {})
        db.commit()
        return row, None
    except Exception as e:
        row.attempts = int(row.attempts or 0) + 1
        row.next_attempt_at = datetime.utcnow() + timedelta(seconds=_backoff_seconds(row.attempts))
        row.last_error = str(e)[:500]
        _bump(db, "notify_outbox_failed")
        db.commit()
        logger.exception("resend_notify_outbox failed id=%s", outbox_id)
        return row, str(e)[:200]


def notify_outbox_metrics(db: Session) -> dict:
    from app.models import NotifyOutbox
    from app.services.app_counters import get_counter

    if not _ensure():
        return {"pending": 0, "failed": 0, "done_today": 0, "counters": {}}
    pending = db.query(NotifyOutbox).filter(NotifyOutbox.done_at.is_(None)).count()
    failed = (
        db.query(NotifyOutbox)
        .filter(NotifyOutbox.done_at.is_(None), NotifyOutbox.attempts > 0)
        .count()
    )
    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = (
        db.query(NotifyOutbox)
        .filter(NotifyOutbox.done_at.isnot(None), NotifyOutbox.done_at >= day_start)
        .count()
    )
    return {
        "pending": pending,
        "failed": failed,
        "done_today": done_today,
        "counters": {
            "enqueued": get_counter(db, "notify_outbox_enqueued"),
            "done": get_counter(db, "notify_outbox_done"),
            "failed": get_counter(db, "notify_outbox_failed"),
            "retried": get_counter(db, "notify_outbox_retried"),
        },
    }
