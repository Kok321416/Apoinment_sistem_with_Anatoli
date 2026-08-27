"""Client–specialist links and diagnostic attempt persistence."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.catalog import DISCLAIMER_RU, get_test
from app.models import ClientCard, ClientSpecialistLink, Consultant, DiagnosticAttempt, DiagnosticInvitation
from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def touch_client_specialist_link(
    db: AsyncSession,
    *,
    client_user_id: int,
    consultant_id: int,
    source: str = "visit",
) -> ClientSpecialistLink:
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
    attempt = DiagnosticAttempt(
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
    db.add(attempt)
    await db.flush()
    return attempt


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
    return list((await db.execute(q)).scalars().all())


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
