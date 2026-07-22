"""Telegram broadcast audience + job processing (Phase 10 / Admin A1)."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Booking,
    Consultant,
    Integration,
    SocialAccount,
    TelegramBroadcastJob,
    TelegramBroadcastRecipient,
    User,
)
from app.services.integration_telegram import normalize_telegram_chat_id

logger = logging.getLogger(__name__)

AUDIENCE_TEST_SELF = "test_self"
AUDIENCE_ALL = "all_unique"
AUDIENCE_CLIENTS = "clients_only"
AUDIENCE_SPECIALISTS = "specialists_only"
AUDIENCE_DUAL = "dual"

VALID_AUDIENCES = frozenset(
    {AUDIENCE_TEST_SELF, AUDIENCE_ALL, AUDIENCE_CLIENTS, AUDIENCE_SPECIALISTS, AUDIENCE_DUAL}
)

AUDIENCE_LABELS = {
    AUDIENCE_TEST_SELF: "Только себе (тест)",
    AUDIENCE_ALL: "Все уникальные chat_id",
    AUDIENCE_CLIENTS: "Только клиенты (opt-in)",
    AUDIENCE_SPECIALISTS: "Только специалисты (Integration)",
    AUDIENCE_DUAL: "Dual (клиент + специалист)",
}

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_COMPLETED = "completed"
JOB_PARTIAL = "partial"
JOB_FAILED = "failed"

REC_PENDING = "pending"
REC_SENT = "sent"
REC_FAILED = "failed"
REC_SKIPPED = "skipped"


def _specialist_chats(db: Session) -> dict[str, int | None]:
    """chat_id -> consultant.user_id (if any). Integration connect = specialist channel consent."""
    out: dict[str, int | None] = {}
    rows = (
        db.query(Integration, Consultant)
        .join(Consultant, Consultant.id == Integration.consultant_id)
        .filter(Integration.telegram_chat_id.isnot(None))
        .filter(Integration.telegram_chat_id != "")
        .filter(Integration.telegram_connected.is_(True))
        .all()
    )
    for integ, consultant in rows:
        if integ.telegram_enabled is False:
            continue
        key = normalize_telegram_chat_id(integ.telegram_chat_id)
        if not key:
            continue
        out[key] = consultant.user_id
    return out


def _client_chats(db: Session) -> dict[str, int | None]:
    """
    Clients with opt-in User.notify_broadcast.
    Sources: SocialAccount(telegram) and Booking.telegram_id linked via client_user_id.
    """
    out: dict[str, int | None] = {}
    opted = {
        int(r[0])
        for r in db.query(User.id).filter(User.notify_broadcast.is_(True), User.is_active.is_(True)).all()
    }
    if not opted:
        return out

    for uid, tg_uid in (
        db.query(SocialAccount.user_id, SocialAccount.uid)
        .filter(SocialAccount.provider == "telegram", SocialAccount.user_id.in_(opted))
        .all()
    ):
        key = normalize_telegram_chat_id(tg_uid)
        if key:
            out[key] = int(uid)

    for tid, cuid in (
        db.query(Booking.telegram_id, Booking.client_user_id)
        .filter(Booking.telegram_id.isnot(None), Booking.client_user_id.in_(opted))
        .all()
    ):
        key = normalize_telegram_chat_id(tid)
        if key and key not in out:
            out[key] = int(cuid) if cuid else None
    return out


def _test_self_chat(db: Session, actor_user_id: int) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.provider == "telegram", SocialAccount.user_id == actor_user_id)
        .first()
    )
    if sa:
        key = normalize_telegram_chat_id(sa.uid)
        if key:
            out[key] = actor_user_id
            return out
    consultant = db.query(Consultant).filter(Consultant.user_id == actor_user_id).first()
    if consultant:
        integ = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
        if integ and integ.telegram_chat_id:
            key = normalize_telegram_chat_id(integ.telegram_chat_id)
            if key:
                out[key] = actor_user_id
    return out


def resolve_audience_chats(
    db: Session,
    audience: str,
    *,
    actor_user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return unique recipients: [{chat_id, user_id, segment}, ...]"""
    audience = (audience or "").strip().lower()
    if audience not in VALID_AUDIENCES:
        return []

    if audience == AUDIENCE_TEST_SELF:
        if not actor_user_id:
            return []
        mapping = _test_self_chat(db, actor_user_id)
        return [{"chat_id": k, "user_id": v, "segment": AUDIENCE_TEST_SELF} for k, v in mapping.items()]

    specialists = _specialist_chats(db)
    clients = _client_chats(db)
    specialist_keys = set(specialists)
    client_keys = set(clients)

    if audience == AUDIENCE_SPECIALISTS:
        keys = specialist_keys
        segment = AUDIENCE_SPECIALISTS
    elif audience == AUDIENCE_CLIENTS:
        keys = client_keys - specialist_keys
        segment = AUDIENCE_CLIENTS
    elif audience == AUDIENCE_DUAL:
        keys = specialist_keys & client_keys
        segment = AUDIENCE_DUAL
    else:  # all_unique
        keys = specialist_keys | client_keys
        segment = AUDIENCE_ALL

    result = []
    for key in sorted(keys):
        uid = specialists.get(key)
        if uid is None:
            uid = clients.get(key)
        result.append({"chat_id": key, "user_id": uid, "segment": segment})
    return result


def dry_run_count(db: Session, audience: str, *, actor_user_id: int | None = None) -> int:
    return len(resolve_audience_chats(db, audience, actor_user_id=actor_user_id))


def create_broadcast_job(
    db: Session,
    *,
    created_by: int,
    audience: str,
    text: str,
) -> tuple[TelegramBroadcastJob | None, str | None]:
    audience = (audience or "").strip().lower()
    text = (text or "").strip()
    if audience not in VALID_AUDIENCES:
        return None, "Неизвестная аудитория"
    if not text:
        return None, "Введите текст рассылки"
    if len(text) > 4000:
        return None, "Текст слишком длинный (макс. 4000 символов)"

    recipients = resolve_audience_chats(db, audience, actor_user_id=created_by)
    if not recipients:
        return None, "Нет получателей для выбранной аудитории (проверьте opt-in / Integration / test_self)"

    job = TelegramBroadcastJob(
        created_by=created_by,
        audience=audience,
        text=text,
        status=JOB_QUEUED,
        recipients_total=len(recipients),
        recipients_sent=0,
        recipients_failed=0,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    for r in recipients:
        db.add(
            TelegramBroadcastRecipient(
                job_id=job.id,
                chat_id=r["chat_id"],
                user_id=r.get("user_id"),
                segment=r.get("segment"),
                status=REC_PENDING,
            )
        )
    db.commit()
    db.refresh(job)
    return job, None


def send_telegram_with_retry(chat_id: str, text: str, *, retries: int = 3) -> tuple[bool, str | None]:
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        return False, "TELEGRAM_BOT_TOKEN not set"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 429:
                retry_after = 1
                try:
                    retry_after = int((r.json().get("parameters") or {}).get("retry_after") or 1)
                except Exception:
                    pass
                time.sleep(min(max(retry_after, 1), 30))
                continue
            if r.status_code >= 400:
                try:
                    desc = (r.json().get("description") or r.text)[:300]
                except Exception:
                    desc = r.text[:300]
                return False, desc or f"HTTP {r.status_code}"
            return True, None
        except Exception as e:
            last_err = str(e)
            time.sleep(0.4 * (attempt + 1))
    return False, last_err or "send failed"


def process_broadcast_jobs(
    db: Session,
    *,
    limit_jobs: int = 3,
    chunk_size: int = 25,
    sleep_between: float = 0.04,
) -> dict[str, int]:
    """Process queued/running jobs in chunks. Safe for cron."""
    stats = {"jobs": 0, "sent": 0, "failed": 0}
    jobs = (
        db.query(TelegramBroadcastJob)
        .filter(TelegramBroadcastJob.status.in_([JOB_QUEUED, JOB_RUNNING]))
        .order_by(TelegramBroadcastJob.id.asc())
        .limit(limit_jobs)
        .all()
    )
    for job in jobs:
        stats["jobs"] += 1
        if job.status == JOB_QUEUED:
            job.status = JOB_RUNNING
            job.started_at = datetime.utcnow()
            db.commit()

        pending = (
            db.query(TelegramBroadcastRecipient)
            .filter(
                TelegramBroadcastRecipient.job_id == job.id,
                TelegramBroadcastRecipient.status == REC_PENDING,
            )
            .order_by(TelegramBroadcastRecipient.id.asc())
            .limit(chunk_size)
            .all()
        )
        for rec in pending:
            ok, err = send_telegram_with_retry(rec.chat_id, job.text)
            if ok:
                rec.status = REC_SENT
                rec.sent_at = datetime.utcnow()
                job.recipients_sent = int(job.recipients_sent or 0) + 1
                stats["sent"] += 1
            else:
                rec.status = REC_FAILED
                rec.error = (err or "error")[:500]
                job.recipients_failed = int(job.recipients_failed or 0) + 1
                stats["failed"] += 1
            db.commit()
            if sleep_between > 0:
                time.sleep(sleep_between)

        left = (
            db.query(TelegramBroadcastRecipient.id)
            .filter(
                TelegramBroadcastRecipient.job_id == job.id,
                TelegramBroadcastRecipient.status == REC_PENDING,
            )
            .first()
        )
        if not left:
            job.finished_at = datetime.utcnow()
            if job.recipients_failed and job.recipients_sent:
                job.status = JOB_PARTIAL
            elif job.recipients_failed and not job.recipients_sent:
                job.status = JOB_FAILED
            else:
                job.status = JOB_COMPLETED
            db.commit()
    return stats


def telegram_stats(db: Session) -> dict[str, int]:
    from sqlalchemy import func

    integrations = (
        db.query(func.count(Integration.id))
        .filter(Integration.telegram_connected.is_(True), Integration.telegram_chat_id.isnot(None))
        .scalar()
        or 0
    )
    client_tg = db.query(func.count(Booking.id)).filter(Booking.telegram_id.isnot(None)).scalar() or 0
    opted = db.query(func.count(User.id)).filter(User.notify_broadcast.is_(True)).scalar() or 0
    jobs = db.query(func.count(TelegramBroadcastJob.id)).scalar() or 0
    return {
        "integrations_connected": int(integrations),
        "bookings_with_telegram": int(client_tg),
        "users_broadcast_opt_in": int(opted),
        "broadcast_jobs_total": int(jobs),
    }
