"""Admin audit helpers (Admin A0)."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AdminAuditLog


def write_admin_audit(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    payload: dict | None = None,
    request: Request | None = None,
) -> None:
    ip = None
    if request is not None:
        ip = request.client.host if request.client else None
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            ip = fwd.split(",")[0].strip()
    db.add(
        AdminAuditLog(
            actor_user_id=actor_user_id,
            action=(action or "")[:64],
            entity=(entity or None) and str(entity)[:64],
            entity_id=(entity_id or None) and str(entity_id)[:64],
            payload_json=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            ip=ip,
            created_at=datetime.utcnow(),
        )
    )
