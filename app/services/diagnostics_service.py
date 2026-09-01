"""Client–specialist links and diagnostic attempt persistence."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.catalog import DISCLAIMER_RU, get_test
from app.models import ClientCard, ClientSpecialistLink, Consultant, DiagnosticAttempt, DiagnosticInvitation
from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

logger = logging.getLogger(__name__)

_DIAGNOSTICS_DDL_READY = False


def _mark_diagnostics_ddl_ready() -> None:
    global _DIAGNOSTICS_DDL_READY
    _DIAGNOSTICS_DDL_READY = True


def reset_diagnostics_ddl_ready_for_tests() -> None:
    """Test helper: allow schema ensure to run again."""
    global _DIAGNOSTICS_DDL_READY
    _DIAGNOSTICS_DDL_READY = False


async def ensure_diagnostics_tables(db: AsyncSession | None = None) -> bool:
    """Create diagnostics tables on first use if deploy patches missed them."""
    global _DIAGNOSTICS_DDL_READY
    if _DIAGNOSTICS_DDL_READY:
        return True

    from app.db_schema import ensure_diagnostics_schema

    ok = False
    try:
        ok = await asyncio.to_thread(ensure_diagnostics_schema)
    except Exception:
        logger.exception("ensure_diagnostics_tables sync failed")

    if ok:
        _mark_diagnostics_ddl_ready()
        return True

    if db is not None:
        try:
            ok = await _ensure_diagnostics_tables_on_session(db) or ok
            if ok:
                _mark_diagnostics_ddl_ready()
                return True
        except Exception:
            logger.exception("ensure_diagnostics_tables async ddl failed")

    return ok


async def ensure_diagnostics_write_ready(db: AsyncSession) -> bool:
    """Ensure diagnostics tables exist before saving an attempt."""
    return await ensure_diagnostics_tables(db)


async def _ensure_diagnostics_tables_on_session(db: AsyncSession) -> bool:
    """Create diagnostics tables on the async session bind (no inspect — avoids MissingGreenlet)."""
    from app.database import Base
    from app.db_schema import _DIAGNOSTICS_TABLES

    def _create(sync_conn) -> None:
        Base.metadata.create_all(bind=sync_conn, tables=list(_DIAGNOSTICS_TABLES))

    conn = await db.connection()
    await conn.run_sync(_create)
    return True


def _is_missing_diagnostics_table(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "no such table" not in msg and "doesn't exist" not in msg:
        return False
    return any(
        name in msg for name in ("diagnostic_attempts", "diagnostic_invitations", "client_specialist_links")
    )


def _skip_diagnostics_read_on_missing_table(exc: BaseException) -> bool:
    """Never run DDL during GET/hub reads — avoids MySQL metadata locks and 500/timeouts."""
    if not _is_missing_diagnostics_table(exc):
        return False
    if _DIAGNOSTICS_DDL_READY:
        logger.error("diagnostics tables missing on read despite startup schema init")
    else:
        logger.warning("diagnostics tables missing on read; startup schema not ready")
    return True


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def touch_client_specialist_link(
    db: AsyncSession,
    *,
    client_user_id: int,
    consultant_id: int,
    source: str = "visit",
) -> ClientSpecialistLink | None:
    if not client_user_id or not consultant_id:
        return None
    if client_user_id and consultant_id:
        # Avoid self-link noise when specialist opens own public URL while logged in.
        owner = (
            await db.execute(select(Consultant.user_id).where(Consultant.id == consultant_id))
        ).scalar_one_or_none()
        if owner and int(owner) == int(client_user_id):
            return None
    try:
        row = (
            await db.execute(
                select(ClientSpecialistLink).where(
                    ClientSpecialistLink.client_user_id == client_user_id,
                    ClientSpecialistLink.consultant_id == consultant_id,
                )
            )
        ).scalar_one_or_none()
        now = datetime.utcnow()
        if row:
            row.last_opened_at = now
            row.is_active = True
            if source and row.source == "visit" and source != "visit":
                row.source = source
            await db.flush()
            return row
        row = ClientSpecialistLink(
            client_user_id=client_user_id,
            consultant_id=consultant_id,
            source=source,
            is_active=True,
            last_opened_at=now,
        )
        db.add(row)
        await db.flush()
        return row
    except (ProgrammingError, OperationalError, DBAPIError) as exc:
        if _skip_diagnostics_read_on_missing_table(exc):
            await db.rollback()
            return None
        raise


async def list_client_psychologists(db: AsyncSession, client_user_id: int) -> list[Consultant]:
    from sqlalchemy.orm import selectinload

    rows = (
        await db.execute(
            select(Consultant)
            .options(selectinload(Consultant.category))
            .join(ClientSpecialistLink, ClientSpecialistLink.consultant_id == Consultant.id)
            .where(
                ClientSpecialistLink.client_user_id == client_user_id,
                ClientSpecialistLink.is_active.is_(True),
            )
            .order_by(ClientSpecialistLink.last_opened_at.desc())
        )
    ).scalars().all()
    return [c for c in rows if consultant_has_feature(c, FEATURE_DIAGNOSTICS)]


async def create_invitation(
    db: AsyncSession,
    *,
    consultant_id: int,
    created_by_user_id: int,
    client_user_id: int | None = None,
    client_card_id: int | None = None,
    test_codes: list[str] | None = None,
    days_valid: int = 14,
    max_uses: int = 3,
) -> tuple[DiagnosticInvitation, str]:
    raw = secrets.token_urlsafe(24)
    inv = DiagnosticInvitation(
        token_hash=hash_invite_token(raw),
        consultant_id=consultant_id,
        client_user_id=client_user_id,
        client_card_id=client_card_id,
        test_codes_json=json.dumps(test_codes or [], ensure_ascii=False),
        expires_at=datetime.utcnow() + timedelta(days=days_valid),
        max_uses=max_uses,
        created_by_user_id=created_by_user_id,
    )
    db.add(inv)
    await db.flush()
    return inv, raw


async def resolve_invitation(db: AsyncSession, raw_token: str) -> DiagnosticInvitation | None:
    if not raw_token:
        return None
    inv = (
        await db.execute(
            select(DiagnosticInvitation).where(
                DiagnosticInvitation.token_hash == hash_invite_token(raw_token)
            )
        )
    ).scalar_one_or_none()
    if not inv:
        return None
    if inv.revoked_at:
        return None
    if inv.expires_at and inv.expires_at < datetime.utcnow():
        return None
    if inv.use_count >= inv.max_uses:
        return None
    return inv


async def complete_attempt(
    db: AsyncSession,
    *,
    attempt: DiagnosticAttempt,
    answers: dict[str, Any],
) -> DiagnosticAttempt:
    test = get_test(attempt.test_code)
    if not test or not test.runnable or not test.score_fn:
        raise ValueError("Тест недоступен для расчёта")
    result = test.score_fn(answers, test)
    attempt.answers_json = json.dumps(answers, ensure_ascii=False)
    attempt.scores_json = json.dumps(result.get("scores") or {}, ensure_ascii=False)
    attempt.scales_json = json.dumps(result.get("scales") or [], ensure_ascii=False)
    attempt.interpretation_json = json.dumps(result.get("interpretation") or {}, ensure_ascii=False)
    attempt.summary_text = (result.get("summary") or "")[:2000]
    attempt.flags_json = json.dumps(result.get("flags") or [], ensure_ascii=False)
    attempt.status = "completed"
    attempt.completed_at = datetime.utcnow()
    await db.flush()
    return attempt


async def start_attempt(
    db: AsyncSession,
    *,
    client_user_id: int,
    consultant_id: int,
    test_code: str,
    source: str = "cabinet",
    invitation_id: int | None = None,
    booking_id: int | None = None,
    client_card_id: int | None = None,
) -> DiagnosticAttempt:
    test = get_test(test_code)
    if not test or not test.runnable:
        raise ValueError("Тест пока недоступен")
    if client_card_id is None:
        card = (
            await db.execute(
                select(ClientCard).where(
                    ClientCard.consultant_id == consultant_id,
                    ClientCard.client_user_id == client_user_id,
                )
            )
        ).scalar_one_or_none()
        client_card_id = card.id if card else None

    base_kwargs = dict(
        client_user_id=client_user_id,
        consultant_id=consultant_id,
        client_card_id=client_card_id,
        invitation_id=invitation_id,
        booking_id=booking_id,
        test_code=test.code,
        test_version=test.version,
        status="in_progress",
        source=source,
        interpretation_json=json.dumps({"disclaimer": DISCLAIMER_RU}, ensure_ascii=False),
    )

    for attempt_no in range(2):
        attempt = DiagnosticAttempt(**base_kwargs)
        db.add(attempt)
        try:
            await db.flush()
            return attempt
        except (ProgrammingError, OperationalError, DBAPIError) as exc:
            if attempt_no == 0 and _is_missing_diagnostics_table(exc):
                logger.warning("diagnostic_attempts missing on insert, re-ensuring schema")
                await db.rollback()
                if not await ensure_diagnostics_write_ready(db):
                    raise RuntimeError("diagnostics schema not available") from exc
                continue
            raise
    raise RuntimeError("diagnostic_attempts insert failed after schema ensure")


async def list_attempts_for_client(
    db: AsyncSession, *, client_user_id: int, consultant_id: int | None = None
) -> list[DiagnosticAttempt]:
    q = select(DiagnosticAttempt).where(
        DiagnosticAttempt.client_user_id == client_user_id,
        DiagnosticAttempt.status == "completed",
    )
    if consultant_id:
        q = q.where(DiagnosticAttempt.consultant_id == consultant_id)
    q = q.order_by(DiagnosticAttempt.completed_at.desc())
    try:
        return list((await db.execute(q)).scalars().all())
    except (ProgrammingError, OperationalError, DBAPIError) as exc:
        if _skip_diagnostics_read_on_missing_table(exc):
            return []
        raise


async def list_attempts_for_card(
    db: AsyncSession, *, consultant_id: int, client_card_id: int
) -> list[DiagnosticAttempt]:
    q = (
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.consultant_id == consultant_id,
            DiagnosticAttempt.client_card_id == client_card_id,
            DiagnosticAttempt.status == "completed",
        )
        .order_by(DiagnosticAttempt.completed_at.desc())
    )
    return list((await db.execute(q)).scalars().all())


def attempt_to_view(attempt: DiagnosticAttempt) -> dict[str, Any]:
    test = get_test(attempt.test_code)
    try:
        scales = json.loads(attempt.scales_json or "[]")
    except json.JSONDecodeError:
        scales = []
    try:
        interpretation = json.loads(attempt.interpretation_json or "{}")
    except json.JSONDecodeError:
        interpretation = {}
    try:
        flags = json.loads(attempt.flags_json or "[]")
    except json.JSONDecodeError:
        flags = []
    return {
        "id": attempt.id,
        "test_code": attempt.test_code,
        "test_version": attempt.test_version,
        "title": test.title if test else attempt.test_code,
        "completed_at": attempt.completed_at,
        "summary": attempt.summary_text,
        "scales": scales,
        "interpretation": interpretation,
        "flags": flags,
        "viz": test.viz if test else "bars",
        "disclaimer": interpretation.get("disclaimer") or DISCLAIMER_RU,
    }
