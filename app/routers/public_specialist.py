"""Public specialist pages: share link → client gate → calendars → services → book."""
from datetime import date, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Calendar, Consultant, Service
from app.services.bookings import create_public_booking
from app.services.email import send_verification_email
from app.services.public_client import (
    clear_client_gate,
    client_gate_ok,
    ensure_public_slug,
    make_email_code,
    set_client_gate,
)
from app.services.slots import get_available_slots
from app.templating import page_context, templates

router = APIRouter(tags=["public-specialist"])
settings = get_settings()


def _get_consultant_by_slug(db: Session, slug: str) -> Consultant:
    consultant = db.query(Consultant).filter(Consultant.public_slug == slug).first()
    if not consultant:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    return consultant


def _sync_booking_session(request: Request) -> None:
    """Mirror client gate into booking_* keys used by create flow."""
    request.session["booking_contact_done"] = True
    request.session["booking_client_name"] = request.session.get("pc_name", "")
    request.session["booking_client_phone"] = request.session.get("pc_phone", "")
    request.session["booking_client_telegram"] = request.session.get("pc_telegram", "")
    request.session["booking_client_email"] = request.session.get("pc_email", "")


def _require_gate(request: Request, consultant: Consultant, next_path: str):
    if client_gate_ok(request.session, consultant.id):
        return None
    return RedirectResponse(f"/s/{consultant.public_slug}/welcome/?{urlencode({'next': next_path})}", status_code=302)


@router.get("/s/{slug}/")
async def specialist_public_home(request: Request, slug: str, db: Session = Depends(get_db)):
    consultant = _get_consultant_by_slug(db, slug)
    gate = _require_gate(request, consultant, f"/s/{slug}/")
    if gate:
        return gate

    calendars = (
        db.query(Calendar)
        .filter(Calendar.consultant_id == consultant.id, Calendar.is_active.is_(True))
        .order_by(Calendar.name)
        .all()
    )
    calendars_data = []
    for cal in calendars:
        svc_count = (
            db.query(Service)
            .filter(Service.calendar_id == cal.id, Service.is_active.is_(True))
            .count()
        )
        calendars_data.append({"calendar": cal, "services_count": svc_count})

    return templates.TemplateResponse(
        "public/specialist.html",
        page_context(
            request,
            db,
            None,
            consultant=consultant,
            calendars_data=calendars_data,
            client_name=request.session.get("pc_name", ""),
            client_email=request.session.get("pc_email", ""),
            client_telegram=request.session.get("pc_telegram", ""),
        ),
    )


@router.get("/s/{slug}/welcome/")
@router.post("/s/{slug}/welcome/")
async def specialist_welcome(request: Request, slug: str, db: Session = Depends(get_db)):
    consultant = _get_consultant_by_slug(db, slug)
    next_url = request.query_params.get("next") or f"/s/{slug}/"
    if not next_url.startswith(f"/s/{slug}"):
        next_url = f"/s/{slug}/"
    error = None

    if request.method == "POST":
        form = await request.form()
        name = (form.get("name") or "").strip()
        channel = (form.get("channel") or "email").strip()
        email = (form.get("email") or "").strip().lower()
        phone = (form.get("phone") or "").strip()
        telegram = (form.get("telegram") or "").strip().lstrip("@")
        if not name:
            error = "Укажите имя"
        elif channel == "email":
            if not email or "@" not in email:
                error = "Укажите корректную почту"
            else:
                code = make_email_code()
                set_client_gate(
                    request.session,
                    consultant_id=consultant.id,
                    name=name,
                    email=email,
                    phone=phone,
                    telegram=telegram,
                    verified=False,
                )
                request.session["pc_email_code"] = code
                request.session["pc_email_pending"] = email
                if not send_verification_email(email, code):
                    error = "Не удалось отправить письмо. Проверьте почту или выберите Телеграм."
                else:
                    q = urlencode({"next": next_url, "email": email})
                    return RedirectResponse(f"/s/{slug}/verify-email/?{q}", status_code=302)
        elif channel == "telegram":
            if not telegram and not phone:
                error = "Укажите ник в Телеграм или телефон"
            else:
                set_client_gate(
                    request.session,
                    consultant_id=consultant.id,
                    name=name,
                    email=email,
                    phone=phone,
                    telegram=telegram or phone,
                    verified=True,
                )
                _sync_booking_session(request)
                return RedirectResponse(next_url, status_code=302)
        else:
            error = "Выберите способ связи: почта или Телеграм"

    return templates.TemplateResponse(
        "public/welcome.html",
        page_context(
            request,
            db,
            None,
            consultant=consultant,
            next_url=next_url,
            error=error,
            bot_username=(settings.telegram_bot_username or "").lstrip("@"),
        ),
    )


@router.get("/s/{slug}/verify-email/")
@router.post("/s/{slug}/verify-email/")
async def specialist_verify_email(request: Request, slug: str, db: Session = Depends(get_db)):
    consultant = _get_consultant_by_slug(db, slug)
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
        page_context(
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
async def specialist_client_logout(request: Request, slug: str, db: Session = Depends(get_db)):
    consultant = _get_consultant_by_slug(db, slug)
    clear_client_gate(request.session)
    for key in (
        "booking_contact_done",
        "booking_client_name",
        "booking_client_phone",
        "booking_client_telegram",
        "booking_client_email",
    ):
        request.session.pop(key, None)
    return RedirectResponse(f"/s/{consultant.public_slug}/welcome/", status_code=302)


@router.get("/s/{slug}/c/{calendar_id}/")
@router.post("/s/{slug}/c/{calendar_id}/")
async def specialist_calendar_book(
    request: Request,
    slug: str,
    calendar_id: int,
    db: Session = Depends(get_db),
):
    consultant = _get_consultant_by_slug(db, slug)
    calendar = (
        db.query(Calendar)
        .filter(
            Calendar.id == calendar_id,
            Calendar.consultant_id == consultant.id,
            Calendar.is_active.is_(True),
        )
        .first()
    )
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")

    gate = _require_gate(request, consultant, f"/s/{slug}/c/{calendar_id}/")
    if gate:
        return gate
    _sync_booking_session(request)

    services = (
        db.query(Service)
        .filter(
            Service.consultant_id == consultant.id,
            Service.is_active.is_(True),
            Service.calendar_id == calendar.id,
        )
        .order_by(Service.name)
        .all()
    )
    # Fallback for legacy services without calendar_id
    if not services:
        services = (
            db.query(Service)
            .filter(
                Service.consultant_id == consultant.id,
                Service.is_active.is_(True),
                Service.calendar_id.is_(None),
            )
            .order_by(Service.name)
            .all()
        )

    error = None
    if request.method == "POST":
        form = await request.form()
        try:
            service_id = int(form.get("service_id") or 0)
            booking_date = datetime.strptime(form.get("booking_date") or "", "%Y-%m-%d").date()
        except (TypeError, ValueError):
            error = "Выберите услугу и дату"
            booking_date = None
            service_id = 0
        booking_time = (form.get("booking_time") or "").strip()
        booking_end = (form.get("booking_end_time") or "").strip()
        if not error:
            booking, err = create_public_booking(
                db,
                calendar,
                service_id,
                booking_date,
                booking_time,
                booking_end,
                request.session.get("pc_name", ""),
                request.session.get("pc_phone", ""),
                request.session.get("pc_email", ""),
                request.session.get("pc_telegram", ""),
            )
            if err:
                error = err
            else:
                return templates.TemplateResponse(
                    "booking_success.html",
                    page_context(
                        request,
                        db,
                        None,
                        booking=booking,
                        calendar=calendar,
                        service=booking.service,
                        consultant=consultant,
                        back_url=f"/s/{slug}/",
                    ),
                )

    return templates.TemplateResponse(
        "public/calendar_book.html",
        page_context(
            request,
            db,
            None,
            consultant=consultant,
            calendar=calendar,
            services=services,
            error=error,
            client_name=request.session.get("pc_name", ""),
            slug=slug,
            today=date.today().isoformat(),
        ),
    )


@router.get("/s/{slug}/c/{calendar_id}/slots/")
async def specialist_calendar_slots(
    slug: str,
    calendar_id: int,
    db: Session = Depends(get_db),
    date: str | None = None,
    service_id: int | None = None,
):
    consultant = _get_consultant_by_slug(db, slug)
    calendar = (
        db.query(Calendar)
        .filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id, Calendar.is_active.is_(True))
        .first()
    )
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")
    if not date or not service_id:
        return {"available_slots": [], "available_windows": []}
    try:
        booking_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"available_slots": [], "available_windows": []}
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.consultant_id == consultant.id, Service.is_active.is_(True))
        .first()
    )
    if not service:
        return {"available_slots": [], "available_windows": []}
    return get_available_slots(db, calendar, service, booking_date)
