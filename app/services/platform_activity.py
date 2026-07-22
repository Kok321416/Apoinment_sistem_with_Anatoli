"""Platform user activity tracking for DAU/WAU (Admin A4)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import PlatformUserActivity


def record_user_activity(db: Session, user_id: int, *, source: str = "login") -> None:
    today = date.today()
    exists = (
        db.query(PlatformUserActivity.id)
        .filter(PlatformUserActivity.user_id == user_id, PlatformUserActivity.activity_date == today)
        .first()
    )
    if exists:
        return
    db.add(
        PlatformUserActivity(
            user_id=user_id,
            activity_date=today,
            source=(source or "login")[:32],
            created_at=datetime.utcnow(),
        )
    )
