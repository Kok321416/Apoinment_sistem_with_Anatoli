"""Invalidate cookie sessions by bumping user.session_version."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User


def invalidate_user_sessions(db: Session, user_id: int) -> tuple[User | None, str | None]:
    user = db.get(User, user_id)
    if not user:
        return None, "Пользователь не найден"
    user.session_version = int(getattr(user, "session_version", 0) or 0) + 1
    db.commit()
    db.refresh(user)
    return user, None
