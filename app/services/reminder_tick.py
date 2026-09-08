"""Throttled background reminder runs for shared hosting without a working HTTP cron.

GitHub keepalive hits GET /health every ~5 minutes. When CRON_SECRET/BOT_API_SECRET
are missing on the server, /internal/cron/reminders/ returns 503 and client/specialist
reminders never fire. This tick restores that path without blocking /health (no await DB).
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Slightly under GitHub's */5 schedule so a delayed ping still gets a run.
_MIN_INTERVAL_SEC = 240
_lock = threading.Lock()
_last_started = 0.0
_running = False


def schedule_reminders_tick(*, force: bool = False) -> bool:
    """Start send_reminders in a daemon thread if the throttle allows. Never blocks."""
    global _last_started, _running

    now = time.monotonic()
    with _lock:
        if _running:
            return False
        if not force and (now - _last_started) < _MIN_INTERVAL_SEC:
            return False
        _last_started = now
        _running = True

    thread = threading.Thread(target=_run_tick, name="reminder-tick", daemon=True)
    thread.start()
    return True


def _run_tick() -> None:
    global _running
    try:
        from app.database import SessionLocal
        from app.services.telegram import send_reminders

        db = SessionLocal()
        try:
            sent = send_reminders(db)
            logger.info(
                "reminder_tick done client_24=%s client_1=%s spec_24=%s spec_1=%s",
                sent.get("client_24", 0),
                sent.get("client_1", 0),
                sent.get("spec_24", 0),
                sent.get("spec_1", 0),
            )
        finally:
            db.close()
    except Exception:
        logger.exception("reminder_tick failed")
    finally:
        with _lock:
            _running = False
