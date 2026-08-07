"""Admin audit log viewer (Admin A5)."""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import AdminAuditLog


def list_admin_audit(
    db: Session,
    *,
    action: str | None = None,
    q: str = "",
    limit: int = 100,
) -> list[AdminAuditLog]:
    query = db.query(AdminAuditLog).order_by(AdminAuditLog.id.desc())
    if action:
        query = query.filter(AdminAuditLog.action == action)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        filters = [
            AdminAuditLog.action.ilike(like),
            AdminAuditLog.entity.ilike(like),
            AdminAuditLog.entity_id.ilike(like),
            AdminAuditLog.payload_json.ilike(like),
        ]
        if q.isdigit():
            filters.append(AdminAuditLog.actor_user_id == int(q))
        query = query.filter(or_(*filters))
    return query.limit(limit).all()


def audit_action_choices(db: Session, *, limit: int = 30) -> list[str]:
    rows = (
        db.query(AdminAuditLog.action)
        .distinct()
        .order_by(AdminAuditLog.action.asc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


async def list_admin_audit_async(
    db,
    *,
    action: str | None = None,
    q: str = "",
    limit: int = 100,
) -> list[AdminAuditLog]:
    from sqlalchemy import or_, select

    stmt = select(AdminAuditLog).order_by(AdminAuditLog.id.desc())
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        filters = [
            AdminAuditLog.action.ilike(like),
            AdminAuditLog.entity.ilike(like),
            AdminAuditLog.entity_id.ilike(like),
            AdminAuditLog.payload_json.ilike(like),
        ]
        if q.isdigit():
            filters.append(AdminAuditLog.actor_user_id == int(q))
        stmt = stmt.where(or_(*filters))
    result = await db.execute(stmt.limit(limit))
    return list(result.scalars().all())


async def audit_action_choices_async(db, *, limit: int = 30) -> list[str]:
    from sqlalchemy import select

    rows = await db.execute(
        select(AdminAuditLog.action).distinct().order_by(AdminAuditLog.action.asc()).limit(limit)
    )
    return [r[0] for r in rows.all() if r[0]]
