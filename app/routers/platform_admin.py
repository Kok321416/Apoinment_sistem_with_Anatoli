"""Platform admin UI: /platform-admin/ (Admin A0 + Telegram Broadcast A1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_platform_admin
from app.models import TelegramBroadcastJob, User
from app.security.csrf import validate_csrf_token
from app.services.admin_audit import write_admin_audit
from app.services.broadcast import (
    AUDIENCE_LABELS,
    VALID_AUDIENCES,
    create_broadcast_job,
    dry_run_count,
    process_broadcast_jobs,
    telegram_stats,
)
from app.templating import templates

router = APIRouter(prefix="/platform-admin", tags=["platform-admin"])


def _csrf_ok(request: Request, form) -> bool:
    token = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
    return validate_csrf_token(request, token)


def _ctx(request: Request, db: Session, user, **extra):
    from app.templating import page_context

    return page_context(request, db, user, platform_admin=True, **extra)


@router.get("/")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_platform_admin(request, db)
    return templates.TemplateResponse(
        "platform_admin/dashboard.html",
        _ctx(request, db, user, nav="dashboard"),
    )


@router.get("/telegram/")
@router.post("/telegram/")
async def admin_telegram(request: Request, db: Session = Depends(get_db)):
    user = require_platform_admin(request, db)
    success = None
    error = None
    dry_run_result = None
    preview_text = ""
    selected_audience = "test_self"

    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу."
        else:
            action = (form.get("action") or "").strip()
            audience = (form.get("audience") or "test_self").strip().lower()
            text = (form.get("text") or "").strip()
            selected_audience = audience if audience in VALID_AUDIENCES else "test_self"
            preview_text = text

            if action == "enable_my_broadcast":
                db_user = db.get(User, user.id)
                if db_user:
                    db_user.notify_broadcast = True
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="broadcast_opt_in_self",
                        entity="user",
                        entity_id=str(user.id),
                        request=request,
                    )
                    db.commit()
                    success = "Рассылки для вашего аккаунта включены (notify_broadcast=true)."
            elif action == "dry_run":
                if audience not in VALID_AUDIENCES:
                    error = "Неизвестная аудитория"
                else:
                    dry_run_result = dry_run_count(db, audience, actor_user_id=user.id)
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="broadcast_dry_run",
                        entity="broadcast",
                        payload={"audience": audience, "count": dry_run_result},
                        request=request,
                    )
                    db.commit()
                    success = f"Dry-run: получателей = {dry_run_result}"
            elif action == "enqueue":
                job, err = create_broadcast_job(
                    db, created_by=user.id, audience=audience, text=text
                )
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="broadcast_enqueue",
                        entity="telegram_broadcast_job",
                        entity_id=str(job.id),
                        payload={"audience": audience, "recipients": job.recipients_total},
                        request=request,
                    )
                    db.commit()
                    # test_self: process immediately for UX
                    if audience == "test_self":
                        process_broadcast_jobs(db, limit_jobs=1, chunk_size=5)
                        db.refresh(job)
                        success = (
                            f"Тестовая рассылка #{job.id}: статус {job.status}, "
                            f"sent={job.recipients_sent}, failed={job.recipients_failed}"
                        )
                    else:
                        success = (
                            f"Job #{job.id} в очереди ({job.recipients_total} получателей). "
                            f"Запустите: python -m app.commands.process_broadcasts"
                        )
            else:
                error = "Неизвестное действие"

    jobs = (
        db.query(TelegramBroadcastJob)
        .order_by(TelegramBroadcastJob.id.desc())
        .limit(20)
        .all()
    )
    stats = telegram_stats(db)
    db_user = db.get(User, user.id)
    my_opt_in = bool(db_user and db_user.notify_broadcast)

    return templates.TemplateResponse(
        "platform_admin/telegram.html",
        _ctx(
            request,
            db,
            user,
            nav="telegram",
            success=success,
            error=error,
            dry_run_result=dry_run_result,
            preview_text=preview_text,
            selected_audience=selected_audience,
            audience_labels=AUDIENCE_LABELS,
            jobs=jobs,
            stats=stats,
            my_opt_in=my_opt_in,
        ),
    )


@router.get("/telegram/jobs/{job_id}/")
async def admin_telegram_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = require_platform_admin(request, db)
    job = db.get(TelegramBroadcastJob, job_id)
    if not job:
        return RedirectResponse("/platform-admin/telegram/", status_code=302)
    from app.models import TelegramBroadcastRecipient

    recipients = (
        db.query(TelegramBroadcastRecipient)
        .filter(TelegramBroadcastRecipient.job_id == job.id)
        .order_by(TelegramBroadcastRecipient.id.asc())
        .limit(200)
        .all()
    )
    return templates.TemplateResponse(
        "platform_admin/telegram_job.html",
        _ctx(request, db, user, nav="telegram", job=job, recipients=recipients),
    )
