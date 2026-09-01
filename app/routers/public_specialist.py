"""Public specialist pages: share link → client gate → calendars → services → book."""
from datetime import date, datetime
from urllib.parse import quote, urlencode
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import get_current_user_async
from app.config import get_settings
from app.database import get_async_db
from app.models import Calendar, Consultant, Service, TimeSlot
from app.services.bookings import create_public_booking_async
from app.services.email import send_verification_email
from app.services.public_client import (
    apply_client_gate_from_user_async,
    clear_client_gate,
    client_gate_ok,
    make_email_code,
    resolve_consultant_by_slug_async,
    set_client_gate,
)
from app.services.slots import get_available_slots_async
from app.templating import page_context_async, templates

router = APIRouter(tags=["public-specialist"])
settings = get_settings()
logger = logging.getLogger(__name__)


async def _get_consultant_by_slug_async(db, slug: str) -> Consultant:
    consultant = await resolve_consultant_by_slug_async(db, slug)
    if not consultant:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    consultant.public_slug = slug
    return consultant


def _sync_booking_session(request: Request) -> None:
    """Mirror client gate into booking_* keys used by create flow."""
    request.session["booking_contact_done"] = True
    request.session["booking_client_name"] = request.session.get("pc_name", "")
    request.session["booking_client_phone"] = request.session.get("pc_phone", "")
    request.session["booking_client_telegram"] = request.session.get("pc_telegram", "")
    request.session["booking_client_email"] = request.session.get("pc_email", "")


async def _require_gate(request: Request, consultant: Consultant, next_path: str, db):
    auth_user = await get_current_user_async(request, db)
    if auth_user:
        await apply_client_gate_from_user_async(
            db,
            request.session,
            consultant_id=consultant.id,
            user=auth_user,
        )
        _sync_booking_session(request)
        return None
    if client_gate_ok(request.session, consultant.id):
        return None
    slug = getattr(consultant, "public_slug", None) or f"id-{consultant.id}"
    return RedirectResponse(f"/s/{slug}/welcome/?{urlencode({'next': next_path})}", status_code=302)


@router.get("/s/{slug}/")
async def specialist_public_home(request: Request, slug: str, db: AsyncSession = Depends(get_async_db)):
    """Public specialist profile. Login is required only when starting a booking."""
    consultant = await _get_consultant_by_slug_async(db, slug)

    auth_user = await get_current_user_async(request, db)
    if auth_user:
        try:
            await apply_client_gate_from_user_async(
                db,
                request.session,
                consultant_id=consultant.id,
                user=auth_user,
            )
            _sync_booking_session(request)
        except Exception:
            logger.exception("client gate apply failed for /s/%s/", slug)

        # Same user opening own public page: skip link write (not a client visit).
        if getattr(auth_user, "id", None) != getattr(consultant, "user_id", None):
            from app.services.diagnostics_service import touch_client_specialist_link

            try:
                await touch_client_specialist_link(
                    db,
                    client_user_id=auth_user.id,
                    consultant_id=consultant.id,
                    source="visit",
                )
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("touch_client_specialist_link failed for /s/%s/", slug)

        # rollback()/commit() can expire ORM state — always reload for the template.
        consultant = await _get_consultant_by_slug_async(db, slug)

    calendars = list(
        (
            await db.execute(
                select(Calendar)
                .where(Calendar.consultant_id == consultant.id, Calendar.is_active.is_(True))
                .order_by(Calendar.name)
            )
        )
        .scalars()
        .all()
    )
    calendars_data = []
    for cal in calendars:
        svc_count = (
            await db.execute(
                select(func.count(Service.id)).where(
                    Service.calendar_id == cal.id,
                    Service.is_active.is_(True),
                )
            )
        ).scalar_one()
        calendars_data.append({"calendar": cal, "services_count": svc_count})

    gated = client_gate_ok(request.session, consultant.id)
    from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

    show_diagnostics = consultant_has_feature(consultant, FEATURE_DIAGNOSTICS)
    return templates.TemplateResponse(
        "public/specialist.html",
        await page_context_async(
            request,
            db,
            auth_user,
            consultant=consultant,
            calendars_data=calendars_data,
            client_name=request.session.get("pc_name", "") if gated else "",
            client_email=request.session.get("pc_email", "") if gated else "",
            client_telegram=request.session.get("pc_telegram", "") if gated else "",
            client_gated=gated,
            welcome_url=f"/s/{slug}/welcome/?next=/s/{slug}/",
            show_diagnostics=show_diagnostics,
            diagnostics_url=f"/s/{slug}/diagnostics/",
        ),
    )


@router.get("/s/{slug}/welcome/")
@router.post("/s/{slug}/welcome/")
async def specialist_welcome(request: Request, slug: str, db: AsyncSession = Depends(get_async_db)):
    """Login gate before public booking (same visual as /login/)."""
    from app.utils.safe_redirect import login_url_with_next, safe_next_url

    from app.services.client_channel import remember_auth_intent, with_client_query

    consultant = await _get_consultant_by_slug_async(db, slug)
    next_url = request.query_params.get("next") or f"/s/{slug}/"
    if not next_url.startswith(f"/s/{slug}"):
        next_url = f"/s/{slug}/"
    next_url = safe_next_url(next_url, default=f"/s/{slug}/")
    welcome_purpose = "diagnostics" if "/diagnostics" in next_url else "booking"
    client_channel = remember_auth_intent(
        request.session,
        next_url=next_url,
        client_channel=request.query_params.get("client"),
    )

    welcome_errors = {
        "yandex_signup": "Не удалось войти через Яндекс. Попробуйте снова.",
        "yandex_failed": "Не удалось войти через Яндекс. Попробуйте другой способ.",
        "vk_signup": "Не удалось войти через VK. Попробуйте снова.",
        "vk_failed": "Не удалось войти через VK. Попробуйте другой способ.",
        "telegram_signup": "Не удалось войти через Телеграм. Попробуйте снова.",
    }
    err_key = request.query_params.get("error") or ""
    error = welcome_errors.get(err_key)

    auth_user = await get_current_user_async(request, db)
    if auth_user:
        await apply_client_gate_from_user_async(
            db, request.session, consultant_id=consultant.id, user=auth_user
        )
        _sync_booking_session(request)
        return RedirectResponse(next_url, status_code=302)

    return templates.TemplateResponse(
        "public/welcome.html",
        await page_context_async(
            request,
            db,
            None,
            consultant=consultant,
            next_url=next_url,
            error=error,
            email=(request.query_params.get("email") or "").strip(),
            login_url=login_url_with_next(next_url, client_channel),
            bot_username=(settings.telegram_bot_username or "").lstrip("@"),
            client_channel=client_channel,
            register_url=with_client_query(
                f"/register/?as=client&next={quote(next_url, safe='')}",
                client_channel,
            ),
            welcome_purpose=welcome_purpose,
        ),
    )


@router.get("/s/{slug}/verify-email/")
@router.post("/s/{slug}/verify-email/")
async def specialist_verify_email(request: Request, slug: str, db: AsyncSession = Depends(get_async_db)):
    consultant = await _get_consultant_by_slug_async(db, slug)
    next_url = request.query_params.get("next") or f"/s/{slug}/"
    email = (request.query_params.get("email") or request.session.get("pc_email_pending") or "").strip()
    error = success = None

    if request.method == "POST":
        form = await request.form()
        email = (form.get("email") or email or "").strip().lower()
        code = (form.get("code") or "").strip()
        expected = (request.session.get("pc_email_code") or "").strip()
        pending = (request.session.get("pc_email_pending") or "").strip().lower()
        if form.get("action") == "resend":
            if not pending:
                error = "Сначала укажите почту на шаге регистрации."
            else:
                new_code = make_email_code()
                request.session["pc_email_code"] = new_code
                if send_verification_email(pending, new_code):
                    success = "Код отправлен повторно."
                    email = pending
                else:
                    error = "Не удалось отправить письмо."
        elif not expected or email != pending:
            error = "Запросите код заново на шаге регистрации."
        elif code != expected:
            error = "Неверный код."
        else:
            set_client_gate(
                request.session,
                consultant_id=consultant.id,
                name=request.session.get("pc_name", ""),
                email=email,
                phone=request.session.get("pc_phone", ""),
                telegram=request.session.get("pc_telegram", ""),
                verified=True,
            )
            request.session.pop("pc_email_code", None)
            request.session.pop("pc_email_pending", None)
            _sync_booking_session(request)
            return RedirectResponse(next_url, status_code=302)

    return templates.TemplateResponse(
        "public/verify_email.html",
        await page_context_async(
            request,
            db,
            None,
            consultant=consultant,
            email=email,
            next_url=next_url,
            error=error,
            success=success,
            email_verify_hours=settings.email_verify_hours,
        ),
    )


@router.get("/s/{slug}/logout-client/")
async def specialist_client_logout(request: Request, slug: str, db: AsyncSession = Depends(get_async_db)):
    await _get_consultant_by_slug_async(db, slug)
    clear_client_gate(request.session)
    for key in (
        "booking_contact_done",
        "booking_client_name",
        "booking_client_phone",
        "booking_client_telegram",
        "booking_client_email",
    ):
        request.session.pop(key, None)
    return RedirectResponse(f"/s/{slug}/welcome/", status_code=302)


@router.get("/s/{slug}/c/{calendar_id}/")
@router.post("/s/{slug}/c/{calendar_id}/")
async def specialist_calendar_book(
    request: Request,
    slug: str,
    calendar_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    consultant = await _get_consultant_by_slug_async(db, slug)
    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
                Calendar.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")

    gate = await _require_gate(request, consultant, f"/s/{slug}/c/{calendar_id}/", db)
    if gate:
        return gate
    _sync_booking_session(request)

    services = list(
        (
            await db.execute(
                select(Service)
                .where(
                    Service.consultant_id == consultant.id,
                    Service.is_active.is_(True),
                    Service.calendar_id == calendar.id,
                )
                .order_by(Service.name)
            )
        )
        .scalars()
        .all()
    )

    error = None
    if request.method == "POST":
        form = await request.form()
        from app.security.csrf import validate_csrf_token

        csrf = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
        if not validate_csrf_token(request, csrf):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
            service_id = 0
            booking_date = None
        else:
            try:
                service_id = int(form.get("service_id") or 0)
                booking_date = datetime.strptime(form.get("booking_date") or "", "%Y-%m-%d").date()
            except (TypeError, ValueError):
                error = "Выберите услугу и дату"
                booking_date = None
                service_id = 0
        booking_time = (form.get("booking_time") or "").strip()
        booking_end = (form.get("booking_end_time") or "").strip()
        client_phone = (form.get("client_phone") or form.get("phone") or "").strip()
        if client_phone:
            request.session["pc_phone"] = client_phone
            request.session["booking_client_phone"] = client_phone
        else:
            client_phone = request.session.get("pc_phone", "")
        if not error and form.get("accept_privacy") != "1":
            error = "Нужно согласие на обработку персональных данных"
        if not error:
            auth_user = await get_current_user_async(request, db)
            booking, err = await create_public_booking_async(
                db,
                calendar,
                service_id,
                booking_date,
                booking_time,
                booking_end,
                request.session.get("pc_name", ""),
                client_phone,
                request.session.get("pc_email", ""),
                request.session.get("pc_telegram", ""),
                client_user_id=(auth_user.id if auth_user else None),
                consultant=consultant,
            )
            if err:
                error = err
            else:
                from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature
                from app.services.diagnostics_service import touch_client_specialist_link

                booked_service = booking.service
                show_diag = consultant_has_feature(consultant, FEATURE_DIAGNOSTICS)
                diag_url = f"/s/{slug}/diagnostics/"
                if auth_user:
                    try:
                        await touch_client_specialist_link(
                            db,
                            client_user_id=auth_user.id,
                            consultant_id=consultant.id,
                            source="booking",
                        )
                        await db.commit()
                    except Exception:
                        await db.rollback()
                return templates.TemplateResponse(
                    "booking_success.html",
                    await page_context_async(
                        request,
                        db,
                        auth_user,
                        booking=booking,
                        calendar=calendar,
                        service=booked_service,
                        consultant=consultant,
                        back_url=f"/s/{slug}/",
                        show_diagnostics_cta=show_diag,
                        diagnostics_url=diag_url,
                    ),
                )

    import json

    weekly: dict[str, list] = {str(i): [] for i in range(7)}
    for slot in (
        await db.execute(
            select(TimeSlot)
            .where(TimeSlot.calendar_id == calendar.id, TimeSlot.is_available.is_(True))
            .order_by(TimeSlot.day_of_week, TimeSlot.start_time)
        )
    ).scalars().all():
        weekly[str(slot.day_of_week)].append(
            {
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
            }
        )

    return templates.TemplateResponse(
        "public/calendar_book.html",
        await page_context_async(
            request,
            db,
            None,
            consultant=consultant,
            calendar=calendar,
            services=services,
            error=error,
            client_name=request.session.get("pc_name", ""),
            client_phone=request.session.get("pc_phone", ""),
            slug=slug,
            today=date.today().isoformat(),
            weekly_windows_json=json.dumps(weekly, ensure_ascii=False),
        ),
    )


@router.get("/s/{slug}/c/{calendar_id}/slots/")
async def specialist_calendar_slots(
    request: Request,
    slug: str,
    calendar_id: int,
    db: AsyncSession = Depends(get_async_db),
    date: str | None = None,
    service_id: int | None = None,
):
    consultant = await _get_consultant_by_slug_async(db, slug)
    if not client_gate_ok(request.session, consultant.id):
        return JSONResponse({"available_slots": [], "available_windows": [], "error": "gate"}, status_code=403)
    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
                Calendar.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")
    if not date or not service_id:
        return {"available_slots": [], "available_windows": []}
    try:
        booking_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"available_slots": [], "available_windows": []}
    service = (
        await db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.consultant_id == consultant.id,
                Service.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not service:
        return {"available_slots": [], "available_windows": []}
    return await get_available_slots_async(db, calendar, service, booking_date)


# --- Diagnostics on specialist public profile (no client cabinet) ---


async def _require_profile_auth(request: Request, consultant: Consultant, next_path: str, db):
    """Logged-in client gate for profile sub-pages (booking, diagnostics)."""
    auth_user = await get_current_user_async(request, db)
    if auth_user:
        await apply_client_gate_from_user_async(
            db,
            request.session,
            consultant_id=consultant.id,
            user=auth_user,
        )
        _sync_booking_session(request)
        return auth_user, None
    if client_gate_ok(request.session, consultant.id):
        return auth_user, None
    slug = getattr(consultant, "public_slug", None) or f"id-{consultant.id}"
    return None, RedirectResponse(
        f"/s/{slug}/welcome/?{urlencode({'next': next_path})}",
        status_code=302,
    )


async def _require_logged_in_client(request: Request, consultant: Consultant, next_path: str, db):
    """Diagnostics and results require a real user account (not gate-only session)."""
    auth_user, redirect = await _require_profile_auth(request, consultant, next_path, db)
    if redirect:
        return None, redirect
    if auth_user:
        return auth_user, None
    slug = getattr(consultant, "public_slug", None) or f"id-{consultant.id}"
    return None, RedirectResponse(
        f"/s/{slug}/welcome/?{urlencode({'next': next_path})}",
        status_code=302,
    )


@router.get("/s/{slug}/diagnostics/")
async def specialist_diagnostics_hub(
    request: Request, slug: str, db: AsyncSession = Depends(get_async_db)
):
    from app.diagnostics.catalog import list_tests
    from app.services.diagnostics_service import (
        attempt_to_view,
        ensure_diagnostics_tables,
        list_attempts_for_client,
        touch_client_specialist_link,
    )
    from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

    consultant = await _get_consultant_by_slug_async(db, slug)
    if not consultant_has_feature(consultant, FEATURE_DIAGNOSTICS):
        raise HTTPException(status_code=404, detail="Диагностика недоступна")
    next_path = f"/s/{slug}/diagnostics/"
    auth_user, redirect = await _require_logged_in_client(request, consultant, next_path, db)
    if redirect:
        return redirect
    await ensure_diagnostics_tables(db)
    if auth_user.id != consultant.user_id:
        try:
            await touch_client_specialist_link(
                db,
                client_user_id=auth_user.id,
                consultant_id=consultant.id,
                source="diagnostics",
            )
            await db.commit()
        except Exception:
            await db.rollback()
    attempts = []
    try:
        attempts = [
            attempt_to_view(a)
            for a in await list_attempts_for_client(
                db, client_user_id=auth_user.id, consultant_id=consultant.id
            )
        ]
    except Exception:
        logger.exception("list_attempts_for_client failed slug=%s user=%s", slug, auth_user.id)
        await db.rollback()
    return templates.TemplateResponse(
        "public/diagnostics_hub.html",
        await page_context_async(
            request,
            db,
            auth_user,
            consultant=consultant,
            public_slug=slug,
            tests=list_tests(only_runnable=False),
            attempts=attempts,
        ),
    )


@router.get("/s/{slug}/diagnostics/tests/{test_code}/")
async def specialist_diagnostics_take(
    request: Request,
    slug: str,
    test_code: str,
    db: AsyncSession = Depends(get_async_db),
):
    from sqlalchemy.orm import selectinload

    from app.diagnostics.catalog import get_test
    from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

    consultant = await _get_consultant_by_slug_async(db, slug)
    if not consultant_has_feature(consultant, FEATURE_DIAGNOSTICS):
        raise HTTPException(status_code=404, detail="Диагностика недоступна")
    test = get_test(test_code)
    if not test or not test.runnable:
        return RedirectResponse(f"/s/{slug}/diagnostics/?error=test", status_code=302)
    next_path = f"/s/{slug}/diagnostics/tests/{test_code}/"
    auth_user, redirect = await _require_logged_in_client(request, consultant, next_path, db)
    if redirect:
        return redirect
    consultant = (
        await db.execute(
            select(Consultant)
            .options(selectinload(Consultant.category))
            .where(Consultant.id == consultant.id)
        )
    ).scalar_one()
    return templates.TemplateResponse(
        "public/diagnostics_take.html",
        await page_context_async(
            request,
            db,
            auth_user,
            consultant=consultant,
            public_slug=slug,
            test=test,
        ),
    )


@router.post("/s/{slug}/diagnostics/tests/{test_code}/submit/")
async def specialist_diagnostics_submit(
    request: Request,
    slug: str,
    test_code: str,
    db: AsyncSession = Depends(get_async_db),
):
    from app.security.csrf import validate_csrf_token
    from app.services.diagnostics_service import (
        complete_attempt,
        start_attempt,
        touch_client_specialist_link,
    )
    from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

    consultant = await _get_consultant_by_slug_async(db, slug)
    if not consultant_has_feature(consultant, FEATURE_DIAGNOSTICS):
        raise HTTPException(status_code=404, detail="Диагностика недоступна")
    next_path = f"/s/{slug}/diagnostics/tests/{test_code}/"
    auth_user, redirect = await _require_logged_in_client(request, consultant, next_path, db)
    if redirect:
        return redirect
    form = await request.form()
    if not validate_csrf_token(request, form.get("csrf_token")):
        return RedirectResponse(f"/s/{slug}/diagnostics/?error=csrf", status_code=302)
    answers = {}
    for key, val in form.multi_items():
        if key.startswith("i") and key[1:].isdigit():
            answers[key] = val
    try:
        attempt = await start_attempt(
            db,
            client_user_id=auth_user.id,
            consultant_id=consultant.id,
            test_code=test_code,
            source=(form.get("source") or "profile").strip() or "profile",
            invitation_id=int(form["invitation_id"]) if form.get("invitation_id") else None,
            booking_id=int(form["booking_id"]) if form.get("booking_id") else None,
        )
        await complete_attempt(db, attempt=attempt, answers=answers)
        await touch_client_specialist_link(
            db,
            client_user_id=auth_user.id,
            consultant_id=consultant.id,
            source="diagnostics",
        )
        await db.commit()
    except ValueError:
        await db.rollback()
        return RedirectResponse(f"/s/{slug}/diagnostics/?error=test", status_code=302)
    except Exception:
        await db.rollback()
        logger.exception(
            "diagnostics submit failed slug=%s test=%s user=%s",
            slug,
            test_code,
            auth_user.id,
        )
        return RedirectResponse(f"/s/{slug}/diagnostics/?error=save", status_code=302)
    return RedirectResponse(f"/s/{slug}/diagnostics/results/{attempt.id}/", status_code=302)


@router.get("/s/{slug}/diagnostics/results/{attempt_id}/")
async def specialist_diagnostics_result(
    request: Request,
    slug: str,
    attempt_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    from app.models import DiagnosticAttempt
    from app.services.diagnostics_service import attempt_to_view
    from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

    consultant = await _get_consultant_by_slug_async(db, slug)
    if not consultant_has_feature(consultant, FEATURE_DIAGNOSTICS):
        raise HTTPException(status_code=404, detail="Диагностика недоступна")
    next_path = f"/s/{slug}/diagnostics/results/{attempt_id}/"
    auth_user, redirect = await _require_logged_in_client(request, consultant, next_path, db)
    if redirect:
        return redirect
    attempt = (
        await db.execute(select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
    ).scalar_one_or_none()
    if (
        not attempt
        or attempt.status != "completed"
        or attempt.consultant_id != consultant.id
        or attempt.client_user_id != auth_user.id
    ):
        return RedirectResponse(f"/s/{slug}/diagnostics/", status_code=302)
    return templates.TemplateResponse(
        "public/diagnostics_result.html",
        await page_context_async(
            request,
            db,
            auth_user,
            consultant=consultant,
            public_slug=slug,
            result=attempt_to_view(attempt),
            attempt=attempt,
        ),
    )
