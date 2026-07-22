"""Persistent app counters (Phase 9 metrics)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AppCounter

DEDUP_HITS_KEY = "notify_dedup_hits"


def increment_counter(db: Session, key: str, *, by: int = 1, commit: bool = False) -> int:
    row = db.get(AppCounter, key)
    if not row:
        row = AppCounter(key=key, value=0, updated_at=datetime.utcnow())
        db.add(row)
        db.flush()
    row.value = int(row.value or 0) + int(by)
    row.updated_at = datetime.utcnow()
    if commit:
        db.commit()
    else:
        db.flush()
    return int(row.value)


def get_counter(db: Session, key: str) -> int:
    row = db.get(AppCounter, key)
    return int(row.value) if row else 0


def record_notify_dedup_hit(db: Session | None = None) -> None:
    """Best-effort: bump counter (flush only; caller commits)."""
    if db is None:
        return
    try:
        increment_counter(db, DEDUP_HITS_KEY, by=1, commit=False)
    except Exception:
        pass
