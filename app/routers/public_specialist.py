"""Public specialist pages: share link → client gate → calendars → services → book."""
from datetime import date, datetime
from urllib.parse import urlencode
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
        ),
    )


@router.get("/s/{slug}/welcome/")
@router.post("/s/{slug}/welcome/")
async def specialist_welcome(request: Request, slug: str, db: AsyncSession = Depends(get_async_db)):
    """Login gate before public booking (same visual as /login/)."""
    from app.utils.safe_redirect import login_url_with_next, safe_next_url

    consultant = await _get_consultant_by_slug_async(db, slug)
    next_url = request.query_params.get("next") or f"/s/{slug}/"
    if not next_url.startswith(f"/s/{slug}"):
        next_url = f"/s/{slug}/"
    next_url = safe_next_url(next_url, default=f"/s/{slug}/")

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
            login_url=login_url_with_next(next_url),
            bot_username=(settings.telegram_bot_username or "").lstrip("@"),
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

                show_diag = consultant_has_feature(consultant, FEATURE_DIAGNOSTICS)
                diag_url = f"/diagnostics/?consultant_id={consultant.id}"
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
                    request.session["diagnostics_consultant_id"] = consultant.id
                else:
                    diag_url = f"/login/?next={diag_url}"
                return templates.TemplateResponse(
                    "booking_success.html",
                    await page_context_async(
                        request,
                        db,
                        auth_user,
                        booking=booking,
                        calendar=calendar,
                        service=booking.service,
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
