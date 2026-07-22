"""Platform error log capture (Admin A2)."""
from __future__ import annotations

import traceback
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PlatformErrorLog

ERROR_STATUSES = frozenset({"new", "in_progress", "fixed", "ignore"})


def record_platform_error(
    *,
    path: str | None,
    method: str | None,
    status_code: int | None,
    message: str | None,
    tb: str | None = None,
    user_id: int | None = None,
    ip: str | None = None,
) -> None:
    db = None
    try:
        db = SessionLocal()
        db.add(
            PlatformErrorLog(
                status="new",
                path=(path or "")[:512] or None,
                method=(method or "")[:16] or None,
                status_code=status_code,
                message=(message or "")[:512] or None,
                traceback=(tb or None) and tb[:20000],
                user_id=user_id,
                ip=ip,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()


def record_exception(request: Request, exc: BaseException, *, user_id: int | None = None) -> None:
    ip = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    record_platform_error(
        path=str(request.url.path),
        method=request.method,
        status_code=500,
        message=f"{type(exc).__name__}: {exc}",
        tb="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        user_id=user_id,
        ip=ip,
    )


def list_errors(db: Session, *, status: str | None = None, limit: int = 50) -> list[PlatformErrorLog]:
    q = db.query(PlatformErrorLog)
    if status and status in ERROR_STATUSES:
        q = q.filter(PlatformErrorLog.status == status)
    return q.order_by(PlatformErrorLog.id.desc()).limit(limit).all()


def set_error_status(db: Session, error_id: int, status: str) -> PlatformErrorLog | None:
    if status not in ERROR_STATUSES:
        return None
    row = db.get(PlatformErrorLog, error_id)
    if not row:
        return None
    row.status = status
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row
