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
    from app.services.platform_admin_users import dashboard_kpi

    return templates.TemplateResponse(
        "platform_admin/dashboard.html",
        _ctx(request, db, user, nav="dashboard", kpi=dashboard_kpi(db)),
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
    from app.services.telegram_copy import sample_template_previews

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
            template_previews=sample_template_previews(),
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


@router.get("/users/")
async def admin_users(request: Request, db: Session = Depends(get_db)):
    user = require_platform_admin(request, db)
    from app.services.platform_admin_users import search_users

    q = (request.query_params.get("q") or "").strip()
    rows = search_users(db, q, limit=50)
    return templates.TemplateResponse(
        "platform_admin/users.html",
        _ctx(request, db, user, nav="users", q=q, users=rows),
    )


@router.post("/users/stop-impersonate/")
async def admin_stop_impersonate(request: Request, db: Session = Depends(get_db)):
    from app.auth.session import get_impersonator_id, stop_impersonation

    form = await request.form()
    if not _csrf_ok(request, form):
        return RedirectResponse("/dashboard/", status_code=302)
    admin_id = get_impersonator_id(request)
    if not admin_id:
        return RedirectResponse("/dashboard/", status_code=302)
    stop_impersonation(request)
    write_admin_audit(
        db,
        actor_user_id=admin_id,
        action="impersonate_stop",
        entity="user",
        request=request,
    )
    db.commit()
    return RedirectResponse("/platform-admin/users/", status_code=302)


@router.get("/users/{user_id}/")
@router.post("/users/{user_id}/")
async def admin_user_detail(request: Request, user_id: int, db: Session = Depends(get_db)):
    admin = require_platform_admin(request, db)
    from app.auth.session import start_impersonation
    from app.services.platform_admin_users import user_admin_card

    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу."
        else:
            action = (form.get("action") or "").strip()
            target = db.get(User, user_id)
            if not target:
                return RedirectResponse("/platform-admin/users/", status_code=302)
            if action == "block":
                if target.id == admin.id:
                    error = "Нельзя заблокировать себя."
                else:
                    target.is_active = False
                    write_admin_audit(
                        db,
                        actor_user_id=admin.id,
                        action="user_block",
                        entity="user",
                        entity_id=str(target.id),
                        request=request,
                    )
                    db.commit()
                    success = "Пользователь заблокирован."
            elif action == "unblock":
                target.is_active = True
                write_admin_audit(
                    db,
                    actor_user_id=admin.id,
                    action="user_unblock",
                    entity="user",
                    entity_id=str(target.id),
                    request=request,
                )
                db.commit()
                success = "Пользователь разблокирован."
            elif action == "broadcast_on":
                target.notify_broadcast = True
                write_admin_audit(
                    db,
                    actor_user_id=admin.id,
                    action="user_broadcast_on",
                    entity="user",
                    entity_id=str(target.id),
                    request=request,
                )
                db.commit()
                success = "notify_broadcast включён."
            elif action == "broadcast_off":
                target.notify_broadcast = False
                write_admin_audit(
                    db,
                    actor_user_id=admin.id,
                    action="user_broadcast_off",
                    entity="user",
                    entity_id=str(target.id),
                    request=request,
                )
                db.commit()
                success = "notify_broadcast выключен."
            elif action == "impersonate":
                if not admin.is_superuser:
                    error = "Impersonate только для superuser."
                elif not target.is_active:
                    error = "Нельзя войти как заблокированный пользователь."
                elif target.id == admin.id:
                    error = "Уже вы."
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=admin.id,
                        action="impersonate_start",
                        entity="user",
                        entity_id=str(target.id),
                        request=request,
                    )
                    db.commit()
                    start_impersonation(request, admin_user_id=admin.id, target_user_id=target.id)
                    return RedirectResponse("/dashboard/", status_code=302)
            else:
                error = "Неизвестное действие"

    card = user_admin_card(db, user_id)
    if not card:
        return RedirectResponse("/platform-admin/users/", status_code=302)
    return templates.TemplateResponse(
        "platform_admin/user_detail.html",
        _ctx(
            request,
            db,
            admin,
            nav="users",
            card=card,
            target=card["user"],
            success=success,
            error=error,
        ),
    )


@router.get("/errors/")
@router.post("/errors/")
async def admin_errors(request: Request, db: Session = Depends(get_db)):
    user = require_platform_admin(request, db)
    from app.services.platform_errors import ERROR_STATUSES, list_errors, set_error_status

    success = error = None
    status_filter = (request.query_params.get("status") or "").strip() or None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        else:
            try:
                eid = int(form.get("error_id") or 0)
            except (TypeError, ValueError):
                eid = 0
            new_status = (form.get("status") or "").strip()
            row = set_error_status(db, eid, new_status) if eid else None
            if row:
                write_admin_audit(
                    db,
                    actor_user_id=user.id,
                    action="error_status",
                    entity="platform_error_log",
                    entity_id=str(row.id),
                    payload={"status": new_status},
                    request=request,
                )
                db.commit()
                success = f"Ошибка #{row.id}: {row.status}"
            else:
                error = "Не удалось обновить статус."
            status_filter = new_status if new_status in ERROR_STATUSES else status_filter

    rows = list_errors(db, status=status_filter, limit=50)
    return templates.TemplateResponse(
        "platform_admin/errors.html",
        _ctx(
            request,
            db,
            user,
            nav="errors",
            errors=rows,
            status_filter=status_filter or "",
            statuses=sorted(ERROR_STATUSES),
            success=success,
            error=error,
        ),
    )
