"""Platform admin UI: /platform-admin/ (A0-A3)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_platform_admin
from app.models import TelegramBroadcastJob, User
from app.models.core import Calendar
from app.security.csrf import validate_csrf_token
from app.services.admin_audit import write_admin_audit
from app.services.admin_rbac import (
    PERM_AUDIT,
    PERM_BILLING,
    PERM_BROADCAST,
    PERM_ERRORS,
    PERM_OPS,
    PERM_SETTINGS,
    PERM_SUPPORT,
    PERM_USERS_READ,
    PERM_USERS_WRITE,
)
from app.services.broadcast import (
    AUDIENCE_LABELS,
    VALID_AUDIENCES,
    create_broadcast_job,
    dry_run_count,
    process_broadcast_jobs,
    telegram_stats,
)
from app.services.platform_admin_access import admin_home_url, admin_permissions, require_admin_permission
from app.templating import templates

router = APIRouter(prefix="/platform-admin", tags=["platform-admin"])


def _csrf_ok(request: Request, form) -> bool:
    token = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
    return validate_csrf_token(request, token)


def _admin(request: Request, db: Session, permission: str | None = None):
    user = require_platform_admin(request, db)
    if permission:
        require_admin_permission(db, user, permission)
    return user


def _ctx(request: Request, db: Session, user, **extra):
    from app.templating import page_context

    return page_context(
        request,
        db,
        user,
        platform_admin=True,
        admin_perms=admin_permissions(db, user),
        **extra,
    )


@router.get("/api/search/")
async def admin_api_search(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db)
    from app.services.platform_admin_search import admin_global_search

    q = (request.query_params.get("q") or "").strip()
    if len(q) == 1:
        return JSONResponse({"results": []})
    results = admin_global_search(db, user, q)
    return JSONResponse({"results": results, "q": q})


@router.get("/api/kpi/")
async def admin_api_kpi(request: Request, db: Session = Depends(get_db)):
    _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_users import dashboard_kpi

    return JSONResponse(dashboard_kpi(db))


@router.get("/api/kpi/stream/")
async def admin_api_kpi_stream(request: Request, db: Session = Depends(get_db)):
    _admin(request, db, PERM_USERS_READ)
    from app.database import SessionLocal
    from app.services.platform_admin_users import dashboard_kpi

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                session = SessionLocal()
                try:
                    payload = json.dumps(dashboard_kpi(session), ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                finally:
                    session.close()
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db)
    home = admin_home_url(db, user)
    if home != "/platform-admin/":
        return RedirectResponse(home, status_code=302)
    require_admin_permission(db, user, PERM_USERS_READ)
    from app.services.platform_admin_users import dashboard_kpi

    return templates.TemplateResponse(
        "platform_admin/dashboard.html",
        _ctx(request, db, user, nav="dashboard", kpi=dashboard_kpi(db)),
    )


@router.get("/telegram/")
@router.post("/telegram/")
async def admin_telegram(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_BROADCAST)
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
                    from app.services.broadcast_gate import record_dry_run

                    record_dry_run(request, audience, dry_run_result)
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
                from app.services.rate_limit import check_rate_limit

                rl_key = f"broadcast:{user.id}"
                if not check_rate_limit(rl_key, max_calls=5, window_sec=300):
                    error = "Слишком много рассылок за 5 минут. Подождите."
                else:
                    count_now = dry_run_count(db, audience, actor_user_id=user.id)
                    from app.services.broadcast_gate import dry_run_allows_enqueue

                    ok_gate, gate_err = dry_run_allows_enqueue(request, audience, count_now)
                    if not ok_gate:
                        error = gate_err
                    else:
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
@router.post("/telegram/jobs/{job_id}/")
async def admin_telegram_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_BROADCAST)
    job = db.get(TelegramBroadcastJob, job_id)
    if not job:
        return RedirectResponse("/platform-admin/telegram/", status_code=302)
    from app.models import TelegramBroadcastRecipient
    from app.services.broadcast import JOB_CANCELLED, JOB_QUEUED, JOB_RUNNING, cancel_broadcast_job

    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        elif (form.get("action") or "").strip() == "stop":
            if job.status not in (JOB_QUEUED, JOB_RUNNING):
                error = "Job уже завершён."
            else:
                stopped, err = cancel_broadcast_job(db, job.id)
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="broadcast_job_stop",
                        entity="telegram_broadcast_job",
                        entity_id=str(job.id),
                        request=request,
                    )
                    db.commit()
                    job = stopped or job
                    success = f"Job #{job.id} остановлен ({JOB_CANCELLED})."
        else:
            error = "Неизвестное действие"

    recipients = (
        db.query(TelegramBroadcastRecipient)
        .filter(TelegramBroadcastRecipient.job_id == job.id)
        .order_by(TelegramBroadcastRecipient.id.asc())
        .limit(200)
        .all()
    )
    return templates.TemplateResponse(
        "platform_admin/telegram_job.html",
        _ctx(
            request,
            db,
            user,
            nav="telegram",
            job=job,
            recipients=recipients,
            success=success,
            error=error,
        ),
    )


@router.get("/users/")
async def admin_users(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
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
    admin = _admin(request, db, PERM_USERS_READ)
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
            from app.services.admin_rbac import has_permission

            if action not in ("impersonate", "assign_role", "revoke_role") and not has_permission(
                db, admin, PERM_USERS_WRITE
            ):
                error = "Недостаточно прав для изменения пользователя."
            elif action == "block":
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
            elif action == "password_reset":
                from app.services.password_reset import send_password_reset_email

                ok, msg = send_password_reset_email(db, target)
                if ok:
                    write_admin_audit(
                        db,
                        actor_user_id=admin.id,
                        action="user_password_reset_email",
                        entity="user",
                        entity_id=str(target.id),
                        request=request,
                    )
                    success = msg
                else:
                    error = msg
            elif action == "invalidate_sessions":
                from app.services.session_invalidation import invalidate_user_sessions

                _, err = invalidate_user_sessions(db, target.id)
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=admin.id,
                        action="user_sessions_invalidate",
                        entity="user",
                        entity_id=str(target.id),
                        request=request,
                    )
                    db.commit()
                    success = "Все cookie-сессии пользователя завершены."
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
                    request.session["session_version"] = int(getattr(target, "session_version", 0) or 0)
                    return RedirectResponse("/dashboard/", status_code=302)
            elif action == "assign_role":
                if not admin.is_superuser:
                    error = "Роли назначает только superuser."
                else:
                    from app.services.admin_rbac import assign_role

                    role = (form.get("role") or "").strip()
                    ok, msg = assign_role(db, user_id=target.id, role=role, granted_by=admin.id)
                    if ok:
                        write_admin_audit(
                            db,
                            actor_user_id=admin.id,
                            action="admin_role_assign",
                            entity="user",
                            entity_id=str(target.id),
                            payload={"role": role},
                            request=request,
                        )
                        success = msg
                    else:
                        error = msg
            elif action == "revoke_role":
                if not admin.is_superuser:
                    error = "Роли снимает только superuser."
                else:
                    from app.services.admin_rbac import revoke_role

                    role = (form.get("role") or "").strip()
                    ok, msg = revoke_role(db, user_id=target.id, role=role)
                    if ok:
                        write_admin_audit(
                            db,
                            actor_user_id=admin.id,
                            action="admin_role_revoke",
                            entity="user",
                            entity_id=str(target.id),
                            payload={"role": role},
                            request=request,
                        )
                        success = msg
                    else:
                        error = msg
            else:
                error = "Неизвестное действие"

    card = user_admin_card(db, user_id)
    if not card:
        return RedirectResponse("/platform-admin/users/", status_code=302)
    from app.services.admin_rbac import ASSIGNABLE_ROLES, ROLE_LABELS, effective_roles, list_role_assignments

    target_user = card["user"]
    return templates.TemplateResponse(
        "platform_admin/user_detail.html",
        _ctx(
            request,
            db,
            admin,
            nav="users",
            card=card,
            target=target_user,
            admin_roles=list_role_assignments(db, target_user.id),
            effective_admin_roles=sorted(effective_roles(db, target_user)),
            assignable_roles=ASSIGNABLE_ROLES,
            role_labels=ROLE_LABELS,
            success=success,
            error=error,
        ),
    )


@router.get("/errors/")
@router.post("/errors/")
async def admin_errors(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_ERRORS)
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


@router.get("/specialists/")
async def admin_specialists(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_domain import search_specialists

    q = (request.query_params.get("q") or "").strip()
    rows = search_specialists(db, q, limit=50)
    return templates.TemplateResponse(
        "platform_admin/specialists.html",
        _ctx(request, db, user, nav="specialists", q=q, specialists=rows),
    )


@router.get("/specialists/{consultant_id}/")
async def admin_specialist_detail(request: Request, consultant_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.config import get_settings
    from app.services.platform_admin_domain import specialist_admin_card
    from app.services.public_client import specialist_public_url

    card = specialist_admin_card(db, consultant_id)
    if not card:
        return RedirectResponse("/platform-admin/specialists/", status_code=302)
    settings = get_settings()
    public_url = specialist_public_url(settings.site_url, card["public_slug"])
    return templates.TemplateResponse(
        "platform_admin/specialist_detail.html",
        _ctx(request, db, user, nav="specialists", card=card, public_url=public_url),
    )


@router.get("/clients/")
async def admin_clients(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_domain import search_platform_clients

    q = (request.query_params.get("q") or "").strip()
    rows = search_platform_clients(db, q, limit=50)
    return templates.TemplateResponse(
        "platform_admin/clients.html",
        _ctx(request, db, user, nav="clients", q=q, clients=rows),
    )


@router.get("/clients/user/{user_id}/")
async def admin_client_user_detail(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_domain import platform_client_detail

    detail = platform_client_detail(db, user_id=user_id)
    if not detail:
        return RedirectResponse("/platform-admin/clients/", status_code=302)
    return templates.TemplateResponse(
        "platform_admin/client_detail.html",
        _ctx(request, db, user, nav="clients", detail=detail),
    )


@router.get("/clients/card/{card_id}/")
async def admin_client_card_detail(request: Request, card_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_domain import platform_client_detail

    detail = platform_client_detail(db, card_id=card_id)
    if not detail:
        return RedirectResponse("/platform-admin/clients/", status_code=302)
    return templates.TemplateResponse(
        "platform_admin/client_detail.html",
        _ctx(request, db, user, nav="clients", detail=detail),
    )


@router.get("/bookings/calendar/")
@router.post("/bookings/calendar/")
async def admin_bookings_calendar(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.bookings_hub import STATUS_LABELS
    from app.services.platform_admin_calendar import (
        bookings_for_week,
        build_week_calendar,
        parse_week_start,
    )
    from app.services.platform_admin_domain import BOOKING_STATUSES, admin_reschedule_booking

    success = error = None
    week_start = parse_week_start(request.query_params.get("week"))
    status_filter = (request.query_params.get("status") or "").strip() or None
    consultant_id_raw = (request.query_params.get("consultant_id") or "").strip()
    calendar_id_raw = (request.query_params.get("calendar_id") or "").strip()
    consultant_id = int(consultant_id_raw) if consultant_id_raw.isdigit() else None
    calendar_id = int(calendar_id_raw) if calendar_id_raw.isdigit() else None

    if request.method == "POST":
        form = await request.form()
        week_start = parse_week_start((form.get("week") or "").strip() or None)
        status_filter = (form.get("status") or "").strip() or None
        consultant_id_raw = (form.get("consultant_id") or "").strip()
        calendar_id_raw = (form.get("calendar_id") or "").strip()
        consultant_id = int(consultant_id_raw) if consultant_id_raw.isdigit() else None
        calendar_id = int(calendar_id_raw) if calendar_id_raw.isdigit() else None
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        elif (form.get("action") or "").strip() == "reschedule":
            try:
                booking_id = int(form.get("booking_id") or 0)
            except (TypeError, ValueError):
                booking_id = 0
            new_date = (form.get("new_date") or "").strip()
            new_time = (form.get("new_time") or "").strip()
            booking, err = admin_reschedule_booking(db, booking_id, new_date, new_time)
            if err:
                error = err
            elif booking:
                write_admin_audit(
                    db,
                    actor_user_id=user.id,
                    action="booking_reschedule",
                    entity="booking",
                    entity_id=str(booking.id),
                    payload={"date": new_date, "time": new_time},
                    request=request,
                )
                db.commit()
                success = f"Запись #{booking.id} перенесена на {new_date} {new_time}"
                week_start = parse_week_start(new_date) if new_date else week_start
        else:
            error = "Неизвестное действие"

    bookings = bookings_for_week(
        db,
        week_start,
        consultant_id=consultant_id,
        calendar_id=calendar_id,
        status=status_filter,
    )
    week = build_week_calendar(bookings, week_start)
    calendar_name = None
    if calendar_id:
        cal = db.get(Calendar, calendar_id)
        calendar_name = cal.name if cal else None

    return templates.TemplateResponse(
        "platform_admin/bookings_calendar.html",
        _ctx(
            request,
            db,
            user,
            nav="bookings",
            week=week,
            status_filter=status_filter or "",
            statuses=BOOKING_STATUSES,
            status_labels=STATUS_LABELS,
            consultant_id=consultant_id_raw,
            calendar_id=calendar_id_raw,
            calendar_name=calendar_name,
            success=success,
            error=error,
        ),
    )


@router.get("/calendars/{calendar_id}/week/")
async def admin_calendar_week(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    cal = db.get(Calendar, calendar_id)
    if not cal:
        return RedirectResponse("/platform-admin/calendars/", status_code=302)
    from app.services.bookings_hub import STATUS_LABELS
    from app.services.platform_admin_calendar import (
        bookings_for_week,
        build_week_calendar,
        parse_week_start,
    )
    from app.services.platform_admin_domain import BOOKING_STATUSES

    week_start = parse_week_start(request.query_params.get("week"))
    status_filter = (request.query_params.get("status") or "").strip() or None
    bookings = bookings_for_week(db, week_start, calendar_id=calendar_id, status=status_filter)
    week = build_week_calendar(bookings, week_start)
    return templates.TemplateResponse(
        "platform_admin/bookings_calendar.html",
        _ctx(
            request,
            db,
            user,
            nav="calendars",
            week=week,
            status_filter=status_filter or "",
            statuses=BOOKING_STATUSES,
            status_labels=STATUS_LABELS,
            consultant_id=str(cal.consultant_id),
            calendar_id=str(calendar_id),
            calendar_name=cal.name,
        ),
    )


@router.get("/bookings/{booking_id}/")
@router.post("/bookings/{booking_id}/")
async def admin_booking_detail(request: Request, booking_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.bookings_hub import STATUS_LABELS
    from app.services.platform_admin_domain import (
        BOOKING_STATUSES,
        admin_reschedule_booking,
        admin_set_booking_status,
        booking_admin_card,
    )

    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        else:
            from app.services.admin_rbac import has_permission

            if not has_permission(db, user, PERM_USERS_WRITE):
                error = "Недостаточно прав для изменения записи."
            else:
                action = (form.get("action") or "").strip()
                new_status = (form.get("status") or "").strip()
                notify = (form.get("notify") or "1") == "1"
                if action == "set_status" and new_status:
                    booking, err = admin_set_booking_status(
                        db, booking_id, new_status, notify=notify
                    )
                    if err:
                        error = err
                    elif booking:
                        write_admin_audit(
                            db,
                            actor_user_id=user.id,
                            action="booking_status",
                            entity="booking",
                            entity_id=str(booking.id),
                            payload={"status": new_status, "notify": notify},
                            request=request,
                        )
                        db.commit()
                        success = f"Статус: {STATUS_LABELS.get(new_status, new_status)}"
                elif action == "reschedule":
                    booking, err = admin_reschedule_booking(
                        db,
                        booking_id,
                        (form.get("new_date") or "").strip(),
                        (form.get("new_time") or "").strip(),
                    )
                    if err:
                        error = err
                    elif booking:
                        write_admin_audit(
                            db,
                            actor_user_id=user.id,
                            action="booking_reschedule",
                            entity="booking",
                            entity_id=str(booking.id),
                            payload={
                                "date": form.get("new_date"),
                                "time": form.get("new_time"),
                            },
                            request=request,
                        )
                        db.commit()
                        success = f"Перенесено на {booking.booking_date} {booking.booking_time}"
                else:
                    error = "Неизвестное действие"

    card = booking_admin_card(db, booking_id)
    if not card:
        return RedirectResponse("/platform-admin/bookings/", status_code=302)
    return templates.TemplateResponse(
        "platform_admin/booking_detail.html",
        _ctx(
            request,
            db,
            user,
            nav="bookings",
            card=card,
            booking=card["booking"],
            statuses=BOOKING_STATUSES,
            status_labels=STATUS_LABELS,
            success=success,
            error=error,
        ),
    )


@router.get("/bookings/")
@router.post("/bookings/")
async def admin_bookings(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.bookings_hub import STATUS_LABELS
    from app.services.platform_admin_domain import (
        BOOKING_STATUSES,
        admin_set_booking_status,
        list_bookings,
    )

    success = error = None
    status_filter = (request.query_params.get("status") or "").strip() or None
    consultant_id_raw = (request.query_params.get("consultant_id") or "").strip()
    consultant_id = int(consultant_id_raw) if consultant_id_raw.isdigit() else None
    q = (request.query_params.get("q") or "").strip()

    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу."
        else:
            action = (form.get("action") or "").strip()
            try:
                booking_id = int(form.get("booking_id") or 0)
            except (TypeError, ValueError):
                booking_id = 0
            new_status = (form.get("status") or "").strip()
            notify = (form.get("notify") or "1") == "1"
            if action == "set_status" and booking_id and new_status:
                booking, err = admin_set_booking_status(
                    db, booking_id, new_status, notify=notify
                )
                if err:
                    error = err
                elif booking:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="booking_status",
                        entity="booking",
                        entity_id=str(booking.id),
                        payload={"status": new_status, "notify": notify},
                        request=request,
                    )
                    db.commit()
                    success = f"Запись #{booking.id}: {STATUS_LABELS.get(new_status, new_status)}"
            else:
                error = "Неизвестное действие"

    bookings = list_bookings(
        db,
        status=status_filter,
        consultant_id=consultant_id,
        q=q,
        limit=50,
    )
    return templates.TemplateResponse(
        "platform_admin/bookings.html",
        _ctx(
            request,
            db,
            user,
            nav="bookings",
            bookings=bookings,
            status_filter=status_filter or "",
            statuses=BOOKING_STATUSES,
            status_labels=STATUS_LABELS,
            consultant_id=consultant_id_raw,
            q=q,
            success=success,
            error=error,
        ),
    )


@router.get("/calendars/")
@router.post("/calendars/")
async def admin_calendars(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.config import get_settings
    from app.services.platform_admin_domain import list_calendars, set_calendar_active
    from app.services.public_client import specialist_public_url

    success = error = None
    consultant_id_raw = (request.query_params.get("consultant_id") or "").strip()
    consultant_id = int(consultant_id_raw) if consultant_id_raw.isdigit() else None
    active_filter = (request.query_params.get("active") or "").strip()
    active_only = True if active_filter == "1" else False if active_filter == "0" else None
    q = (request.query_params.get("q") or "").strip()

    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        else:
            action = (form.get("action") or "").strip()
            try:
                calendar_id = int(form.get("calendar_id") or 0)
            except (TypeError, ValueError):
                calendar_id = 0
            if action in ("enable", "disable") and calendar_id:
                cal = set_calendar_active(db, calendar_id, is_active=(action == "enable"))
                if cal:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="calendar_enable" if action == "enable" else "calendar_disable",
                        entity="calendar",
                        entity_id=str(cal.id),
                        request=request,
                    )
                    db.commit()
                    success = f"Календарь #{cal.id}: {'включён' if cal.is_active else 'отключён'}"
                else:
                    error = "Календарь не найден"
            else:
                error = "Неизвестное действие"

    rows = list_calendars(
        db,
        consultant_id=consultant_id,
        active_only=active_only,
        q=q,
        limit=50,
    )
    settings = get_settings()
    for row in rows:
        row["public_url"] = specialist_public_url(settings.site_url, row["public_slug"])
        if row["calendar"]:
            row["booking_url"] = f"{row['public_url']}c/{row['calendar'].id}/"
    return templates.TemplateResponse(
        "platform_admin/calendars.html",
        _ctx(
            request,
            db,
            user,
            nav="calendars",
            calendars=rows,
            consultant_id=consultant_id_raw,
            active_filter=active_filter,
            q=q,
            success=success,
            error=error,
        ),
    )


@router.get("/security/")
@router.post("/security/")
async def admin_security(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db)
    from app.models import User
    from app.services.admin_totp import (
        admin_2fa_enabled,
        disable_admin_2fa,
        enable_admin_2fa,
        ensure_admin_2fa_setup,
        provisioning_uri,
    )
    from app.services.platform_admin_domain import list_failed_logins, list_security_events

    success = error = None
    db_user = db.get(User, user.id)
    totp_row = ensure_admin_2fa_setup(db, db_user) if db_user else None
    if request.method == "POST" and db_user:
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        else:
            action = (form.get("action") or "").strip()
            code = (form.get("code") or "").strip()
            if action == "enable_2fa":
                ok, msg = enable_admin_2fa(db, db_user, code)
                if ok:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="admin_2fa_enable",
                        entity="user",
                        entity_id=str(user.id),
                        request=request,
                    )
                    db.commit()
                    success = msg
                else:
                    error = msg
            elif action == "disable_2fa":
                if not user.is_superuser:
                    error = "Отключение 2FA только для superuser (или обратитесь к нему)."
                elif not code:
                    error = "Введите текущий код"
                else:
                    from app.services.admin_totp import verify_admin_2fa_login

                    if not verify_admin_2fa_login(db, user.id, code):
                        error = "Неверный код"
                    else:
                        disable_admin_2fa(db, user.id)
                        write_admin_audit(
                            db,
                            actor_user_id=user.id,
                            action="admin_2fa_disable",
                            entity="user",
                            entity_id=str(user.id),
                            request=request,
                        )
                        db.commit()
                        success = "2FA отключена"
                        totp_row = None
            else:
                error = "Неизвестное действие"
        if db_user:
            totp_row = ensure_admin_2fa_setup(db, db_user)

    totp_uri = provisioning_uri(totp_row.secret, user.email or user.username) if totp_row else ""
    return templates.TemplateResponse(
        "platform_admin/security.html",
        _ctx(
            request,
            db,
            user,
            nav="security",
            failed_logins=list_failed_logins(db, limit=40),
            security_events=list_security_events(db, limit=40),
            totp_enabled=admin_2fa_enabled(db, user.id),
            totp_secret=totp_row.secret if totp_row and not admin_2fa_enabled(db, user.id) else "",
            totp_uri=totp_uri,
            success=success,
            error=error,
        ),
    )


@router.get("/email/")
@router.post("/email/")
async def admin_email(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_SETTINGS)
    from app.services.platform_email_log import list_email_deliveries, resend_email_delivery

    success = error = None
    status_filter = (request.query_params.get("status") or "").strip() or None
    q = (request.query_params.get("q") or "").strip()

    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        else:
            action = (form.get("action") or "").strip()
            try:
                log_id = int(form.get("log_id") or 0)
            except (TypeError, ValueError):
                log_id = 0
            if action == "resend" and log_id:
                from app.services.rate_limit import check_rate_limit

                if not check_rate_limit(f"email_resend:{user.id}", max_calls=10, window_sec=300):
                    error = "Слишком много resend за 5 минут."
                else:
                    row, err = resend_email_delivery(db, log_id)
                    if err:
                        error = err
                    else:
                        write_admin_audit(
                            db,
                            actor_user_id=user.id,
                            action="email_resend",
                            entity="email_delivery_log",
                            entity_id=str(log_id),
                            request=request,
                        )
                        db.commit()
                        success = f"Повторная отправка на {row.to_email if row else '?'}"
            else:
                error = "Неизвестное действие"

    rows = list_email_deliveries(db, status=status_filter, q=q, limit=50)
    return templates.TemplateResponse(
        "platform_admin/email.html",
        _ctx(
            request,
            db,
            user,
            nav="email",
            emails=rows,
            status_filter=status_filter or "",
            q=q,
            success=success,
            error=error,
        ),
    )


@router.get("/analytics/")
async def admin_analytics(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_analytics import analytics_snapshot

    return templates.TemplateResponse(
        "platform_admin/analytics.html",
        _ctx(request, db, user, nav="analytics", metrics=analytics_snapshot(db)),
    )


@router.get("/settings/")
async def admin_settings(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_SETTINGS)
    from app.config import get_settings
    from app.services.platform_admin_settings import integration_status, platform_flags

    settings = get_settings()
    return templates.TemplateResponse(
        "platform_admin/settings.html",
        _ctx(
            request,
            db,
            user,
            nav="settings",
            integrations=integration_status(settings),
            flags=platform_flags(settings),
        ),
    )


@router.get("/audit/")
async def admin_audit(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_AUDIT)
    from app.services.platform_admin_audit import audit_action_choices, list_admin_audit

    action_filter = (request.query_params.get("action") or "").strip() or None
    q = (request.query_params.get("q") or "").strip()
    rows = list_admin_audit(db, action=action_filter, q=q, limit=100)
    return templates.TemplateResponse(
        "platform_admin/audit.html",
        _ctx(
            request,
            db,
            user,
            nav="audit",
            audit_rows=rows,
            action_filter=action_filter or "",
            actions=audit_action_choices(db),
            q=q,
        ),
    )


@router.get("/ops/")
@router.post("/ops/")
async def admin_ops(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_OPS)
    from app.config import get_settings
    from app.services.platform_admin_ops import create_platform_backup, system_snapshot

    settings = get_settings()
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        elif not user.is_superuser:
            error = "Backup только для superuser."
        else:
            action = (form.get("action") or "").strip()
            if action == "backup":
                path, err = create_platform_backup(settings)
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="platform_backup",
                        entity="backup",
                        entity_id=path,
                        request=request,
                    )
                    db.commit()
                    success = f"Backup создан: {path}"
            else:
                error = "Неизвестное действие"

    snap = system_snapshot(db, settings)
    return templates.TemplateResponse(
        "platform_admin/ops.html",
        _ctx(request, db, user, nav="ops", snap=snap, success=success, error=error),
    )


@router.get("/support/")
async def admin_support_list(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_SUPPORT)
    from app.services.platform_support import TICKET_STATUSES, TICKET_STATUS_LABELS, list_support_tickets

    status_filter = (request.query_params.get("status") or "").strip() or None
    q = (request.query_params.get("q") or "").strip()
    tickets = list_support_tickets(db, status=status_filter, q=q, limit=50)
    return templates.TemplateResponse(
        "platform_admin/support.html",
        _ctx(
            request,
            db,
            user,
            nav="support",
            tickets=tickets,
            statuses=TICKET_STATUSES,
            status_labels=TICKET_STATUS_LABELS,
            status_filter=status_filter or "",
            q=q,
        ),
    )


@router.get("/support/{ticket_id}/")
@router.post("/support/{ticket_id}/")
async def admin_support_detail(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_SUPPORT)
    from app.services.platform_support import (
        TICKET_STATUSES,
        TICKET_STATUS_LABELS,
        reply_support_ticket,
        set_ticket_status,
        ticket_detail,
    )

    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        else:
            action = (form.get("action") or "").strip()
            if action == "reply":
                _, err = reply_support_ticket(
                    db,
                    ticket_id,
                    author_user_id=user.id,
                    body=form.get("body") or "",
                    is_staff=True,
                )
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="support_reply",
                        entity="support_ticket",
                        entity_id=str(ticket_id),
                        request=request,
                    )
                    db.commit()
                    success = "Ответ отправлен"
            elif action == "set_status":
                _, err = set_ticket_status(db, ticket_id, form.get("status") or "")
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="support_status",
                        entity="support_ticket",
                        entity_id=str(ticket_id),
                        payload={"status": form.get("status")},
                        request=request,
                    )
                    db.commit()
                    success = "Статус обновлён"
            else:
                error = "Неизвестное действие"

    detail = ticket_detail(db, ticket_id)
    if not detail:
        return RedirectResponse("/platform-admin/support/", status_code=302)
    return templates.TemplateResponse(
        "platform_admin/support_detail.html",
        _ctx(
            request,
            db,
            user,
            nav="support",
            ticket=detail["ticket"],
            messages=detail["messages"],
            ticket_user=detail["user"],
            statuses=TICKET_STATUSES,
            status_labels=TICKET_STATUS_LABELS,
            success=success,
            error=error,
        ),
    )


@router.get("/billing/")
@router.post("/billing/")
async def admin_billing(request: Request, db: Session = Depends(get_db)):
    user = _admin(request, db, PERM_BILLING)
    from app.services.platform_billing import (
        billing_snapshot,
        create_billing_plan,
        list_billing_plans,
        toggle_plan_active,
    )

    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _csrf_ok(request, form):
            error = "Ошибка безопасности."
        elif not user.is_superuser:
            error = "Тарифы управляет superuser."
        else:
            action = (form.get("action") or "").strip()
            if action == "create_plan":
                try:
                    price = int(form.get("price_rub") or 0)
                except (TypeError, ValueError):
                    price = -1
                plan, err = create_billing_plan(
                    db,
                    code=form.get("code") or "",
                    name=form.get("name") or "",
                    price_rub=price,
                    interval=form.get("interval") or "month",
                )
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="billing_plan_create",
                        entity="billing_plan",
                        entity_id=str(plan.id),
                        request=request,
                    )
                    db.commit()
                    success = f"Тариф {plan.code} создан"
            elif action == "toggle_plan":
                try:
                    plan_id = int(form.get("plan_id") or 0)
                except (TypeError, ValueError):
                    plan_id = 0
                plan, err = toggle_plan_active(db, plan_id)
                if err:
                    error = err
                else:
                    write_admin_audit(
                        db,
                        actor_user_id=user.id,
                        action="billing_plan_toggle",
                        entity="billing_plan",
                        entity_id=str(plan.id),
                        request=request,
                    )
                    db.commit()
                    success = f"Тариф {plan.code}: {'active' if plan.is_active else 'off'}"
            else:
                error = "Неизвестное действие"

    plans = list_billing_plans(db)
    return templates.TemplateResponse(
        "platform_admin/billing.html",
        _ctx(
            request,
            db,
            user,
            nav="billing",
            snap=billing_snapshot(db),
            plans=plans,
            success=success,
            error=error,
        ),
    )


@router.get("/export/users.csv")
async def admin_export_users(request: Request, db: Session = Depends(get_db)):
    _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_export import export_filename, export_users_csv

    content = export_users_csv(db)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export_filename("users")}"'},
    )


@router.get("/export/bookings.csv")
async def admin_export_bookings(request: Request, db: Session = Depends(get_db)):
    _admin(request, db, PERM_USERS_READ)
    from app.services.platform_admin_export import export_filename, export_bookings_csv

    content = export_bookings_csv(db)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export_filename("bookings")}"'},
    )
