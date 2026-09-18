"""Durable at-least-once queue for booking notifications."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 12
RETRY_BASE_SEC = 60


def enqueue_status_changed(db: Session, booking_id: int, old_status: str | None) -> int | None:
    """Persist outbox row. Safe if table missing (returns None)."""
    try:
        from app.db_schema import ensure_notify_outbox_schema
        from app.models import NotifyOutbox

        if not ensure_notify_outbox_schema():
            return None
        row = NotifyOutbox(
            kind="status_changed",
            booking_id=int(booking_id),
            payload_json=json.dumps({"old_status": old_status}, ensure_ascii=False),
            attempts=0,
            next_attempt_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return int(row.id)
    except Exception:
        logger.exception("enqueue_status_changed failed booking_id=%s", booking_id)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def mark_outbox_done(db: Session, outbox_id: int | None) -> None:
    if not outbox_id:
        return
    try:
        from app.models import NotifyOutbox

        row = db.get(NotifyOutbox, int(outbox_id))
        if row and not row.done_at:
            row.done_at = datetime.utcnow()
            db.flush()
    except Exception:
        logger.exception("mark_outbox_done failed id=%s", outbox_id)


def _backoff_seconds(attempts: int) -> int:
    return min(3600, RETRY_BASE_SEC * max(1, 2 ** max(0, attempts - 1)))


def process_notify_outbox(db: Session, *, limit: int = 30) -> dict:
    """Retry pending status_changed (and future kinds). Called from reminder tick."""
    from app.db_schema import ensure_notify_outbox_schema
    from app.models import NotifyOutbox
    from app.services.notify_bridge import _load_booking
    from app.services.telegram import notify_booking_status_changed

    stats = {"processed": 0, "done": 0, "failed": 0, "skipped": 0}
    if not ensure_notify_outbox_schema():
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
            if row.kind == "status_changed" and row.booking_id:
                booking = _load_booking(db, int(row.booking_id))
                if not booking:
                    row.done_at = now
                    row.last_error = "booking_missing"
                    stats["done"] += 1
                    continue
                notify_booking_status_changed(db, booking, payload.get("old_status"))
                row.done_at = now
                row.last_error = None
                stats["done"] += 1
            else:
                row.done_at = now
                row.last_error = f"unknown_kind:{row.kind}"
                stats["skipped"] += 1
        except Exception as e:
            row.attempts = int(row.attempts or 0) + 1
            row.next_attempt_at = now + timedelta(seconds=_backoff_seconds(row.attempts))
            row.last_error = str(e)[:500]
            stats["failed"] += 1
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
