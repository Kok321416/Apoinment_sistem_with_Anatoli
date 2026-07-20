import os
import shutil
import uuid
from datetime import date, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.auth.session import get_current_user, login_user, logout_user
from app.config import get_settings
from app.database import get_db
from app.deps import get_consultant, normalize_url
from app.models import (
    Booking,
    Calendar,
    Category,
    ClientCard,
    Consultant,
    EmailAddress,
    Integration,
    Service,
    SocialAccount,
    TimeSlot,
    User,
)
from app.security.csrf import validate_csrf_token
from app.services.bookings import create_public_booking, mark_past_bookings_completed, parse_fio
from app.services.email_verification import ensure_email_address, resend_verification_email, send_user_verification_email
from app.services.slots import get_available_slots
from app.services.telegram import notify_booking_status_changed
from app.templating import page_context, templates

router = APIRouter(tags=["pages"])
settings = get_settings()
DAYS_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _form_csrf_ok(request: Request, form) -> bool:
    token = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
    return validate_csrf_token(request, token)


def _optional_user(request: Request, db: Session):
    return get_current_user(request, db)


def _require_user(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None
    return user


@router.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    return templates.TemplateResponse("home.html", page_context(request, db, user))


@router.get("/privacy/")
@router.get("/terms/")
async def legal_pages(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    template = "privacy.html" if request.url.path.startswith("/privacy") else "terms.html"
    return templates.TemplateResponse(template, page_context(request, db, user))


@router.get("/register/")
@router.post("/register/")
async def register_page(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    if user:
        return RedirectResponse("/", status_code=302)
    error = fio = phone = email = None
    if request.method == "POST":
        form = await request.form()
        fio = (form.get("fio") or "").strip()
        phone = (form.get("phone") or "").strip()
        auth_method = form.get("auth_method", "email")
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
        elif not fio or not phone:
            error = "Укажите ФИО и номер телефона"
        elif auth_method == "yandex":
            error = "Вход через Яндекс будет доступен позже."
        elif auth_method == "telegram":
            request.session["register_fio"] = fio
            request.session["register_phone"] = phone
            return RedirectResponse(f"/accounts/telegram/login/?{urlencode({'process': 'signup', 'next': '/'})}", status_code=302)
        else:
            email = (form.get("email") or "").strip()
            password = form.get("password", "")
            password_confirm = form.get("password_confirm", "")
            if not email or not password:
                error = "Укажите email и пароль"
            elif password != password_confirm:
                error = "Пароли не совпадают"
            elif db.query(User).filter(User.username == email).first():
                error = "Пользователь с таким email уже зарегистрирован"
            else:
                first_name, last_name, middle_name = parse_fio(fio)
                new_user = User(
                    username=email, email=email, password=hash_password(password),
                    is_active=False, date_joined=datetime.utcnow(),
                )
                db.add(new_user)
                db.flush()
                category = db.query(Category).filter(Category.name_category == "Общая").first()
                if not category:
                    category = Category(name_category="Общая")
                    db.add(category)
                    db.flush()
                db.add(Consultant(
                    user_id=new_user.id, first_name=first_name, last_name=last_name,
                    middle_name=middle_name, email=email, phone=phone,
                    telegram_nickname="", category_of_specialist_id=category.id,
                ))
                ensure_email_address(db, new_user, email, verified=False)
                if not send_user_verification_email(db, new_user):
                    db.rollback()
                    error = "Не удалось отправить письмо. Проверьте email или обратитесь к администратору."
                else:
                    return templates.TemplateResponse("email_verification_sent.html", page_context(
                        request, db, user, email=email,
                    ))
    return templates.TemplateResponse("register.html", page_context(request, db, user, error=error, fio=fio, phone=phone, email=email))


@router.get("/login/")
@router.post("/login/")
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    if user:
        return RedirectResponse("/", status_code=302)
    error = success = None
    if request.query_params.get("verified") == "1":
        success = "Email подтверждён. Теперь можно войти."
    if request.query_params.get("error") == "telegram_expired":
        error = "Ссылка входа через Telegram истекла. Попробуйте снова."
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
        elif form.get("action") == "resend_verification":
            email_resend = form.get("email", "")
            ok, msg = resend_verification_email(db, email_resend)
            if ok:
                success = msg
            else:
                error = msg
        else:
            email = form.get("email")
            password = form.get("password")
            if not email or not password:
                error = "Заполните все поля"
            else:
                db_user = db.query(User).filter(User.username == email).first()
                if not db_user or not verify_password(password, db_user.password):
                    error = "Неверный email или пароль"
                elif not db_user.is_active:
                    error = "Подтвердите email. Проверьте почту или отправьте письмо повторно ниже."
                else:
                    login_user(request, db_user)
                    return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", page_context(
        request, db, user, error=error, success=success,
        resend_email=request.query_params.get("email", ""),
    ))


@router.post("/logout/")
async def logout_page(request: Request):
    form = await request.form()
    if _form_csrf_ok(request, form):
        logout_user(request)
    return RedirectResponse("/", status_code=302)


@router.get("/calendars/")
@router.post("/calendars/")
async def calendars_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "create_calendar":
            name = form.get("name")
            color = form.get("color", "#667eea")
            if name:
                db.add(Calendar(consultant_id=consultant.id, name=name, color=color))
                db.commit()
                success = "Календарь создан успешно!"
            else:
                error = "Укажите название календаря"
        elif action == "delete_calendar":
            cal = db.query(Calendar).filter(Calendar.id == int(form.get("calendar_id")), Calendar.consultant_id == consultant.id).first()
            if cal:
                db.delete(cal)
                db.commit()
                success = "Календарь удален"
            else:
                error = "Календарь не найден"
    calendars = db.query(Calendar).filter(Calendar.consultant_id == consultant.id).order_by(Calendar.name).all()
    calendars_with_links = [{"calendar": c, "booking_url": f"{settings.site_url}/book/{c.id}/"} for c in calendars]
    return templates.TemplateResponse("calendars.html", page_context(
        request, db, user, calendars=calendars, calendars_with_links=calendars_with_links,
        success=success, error=error,
    ))


@router.get("/calendars/{calendar_id}/")
@router.post("/calendars/{calendar_id}/")
async def calendar_detail(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id).first()
    if not calendar:
        return RedirectResponse("/calendars/", status_code=302)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "add_time_slot":
            if form.get("day_of_week") and form.get("start_time") and form.get("end_time"):
                db.add(TimeSlot(
                    calendar_id=calendar.id, day_of_week=int(form.get("day_of_week")),
                    start_time=datetime.strptime(form.get("start_time"), "%H:%M").time(),
                    end_time=datetime.strptime(form.get("end_time"), "%H:%M").time(),
                ))
                db.commit()
                success = "Временное окно добавлено!"
            else:
                error = "Заполните все поля"
        elif action == "delete_time_slot":
            slot = db.query(TimeSlot).filter(TimeSlot.id == int(form.get("slot_id")), TimeSlot.calendar_id == calendar.id).first()
            if slot:
                db.delete(slot)
                db.commit()
                success = "Временное окно удалено"
            else:
                error = "Временное окно не найдено"
    time_slots_by_day = {
        d: db.query(TimeSlot).filter(TimeSlot.calendar_id == calendar.id, TimeSlot.day_of_week == d).order_by(TimeSlot.start_time).all()
        for d in range(7)
    }
    return templates.TemplateResponse("calendar_detail.html", page_context(
        request, db, user, calendar=calendar, time_slots_by_day=time_slots_by_day,
        days_names=DAYS_NAMES, days_short=DAYS_SHORT, success=success, error=error,
    ))


@router.get("/calendars/{calendar_id}/settings/")
@router.post("/calendars/{calendar_id}/settings/")
async def calendar_settings(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id).first()
    if not calendar:
        return RedirectResponse("/calendars/", status_code=302)
    if request.method == "POST":
        form = await request.form()
        calendar.break_between_services_minutes = int(form.get("break_between_services_minutes", 0) or 0)
        calendar.book_ahead_hours = int(form.get("book_ahead_hours", 24) or 24)
        calendar.max_services_per_day = int(form.get("max_services_per_day", 0) or 0)
        calendar.reminder_hours_first = int(form.get("reminder_hours_first", 24) or 24)
        calendar.reminder_hours_second = int(form.get("reminder_hours_second", 1) or 1)
        db.commit()
        return RedirectResponse(f"/calendars/{calendar.id}/", status_code=302)
    return templates.TemplateResponse("calendar_settings_edit.html", page_context(request, db, user, calendar=calendar))


@router.get("/services/")
@router.post("/services/")
async def services_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "create_service":
            name = form.get("name")
            if name:
                db.add(Service(
                    consultant_id=consultant.id, name=name,
                    description=form.get("description", ""),
                    duration_minutes=int(form.get("duration_minutes", 60) or 60),
                    price=form.get("price") or None,
                ))
                db.commit()
                success = "Услуга создана успешно!"
            else:
                error = "Укажите название услуги"
        elif action == "toggle_service":
            svc = db.query(Service).filter(Service.id == int(form.get("service_id")), Service.consultant_id == consultant.id).first()
            if svc:
                svc.is_active = not svc.is_active
                db.commit()
                success = "Статус услуги изменен"
        elif action == "delete_service":
            svc = db.query(Service).filter(Service.id == int(form.get("service_id")), Service.consultant_id == consultant.id).first()
            if svc:
                db.delete(svc)
                db.commit()
                success = "Услуга удалена"
    services = db.query(Service).filter(Service.consultant_id == consultant.id).order_by(Service.name).all()
    return templates.TemplateResponse("services.html", page_context(request, db, user, services=services, success=success, error=error))


@router.get("/book/")
async def book_redirect(db: Session = Depends(get_db)):
    calendar = db.query(Calendar).filter(Calendar.is_active.is_(True)).order_by(Calendar.id).first()
    if not calendar:
        raise HTTPException(status_code=404, detail="Нет доступных календарей")
    return RedirectResponse(f"/book/{calendar.id}/", status_code=302)


@router.get("/book/{calendar_id}/")
@router.post("/book/{calendar_id}/")
async def public_booking(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.is_active.is_(True)).first()
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")
    consultant = db.query(Consultant).filter(Consultant.id == calendar.consultant_id).first()
    calendar.consultant = consultant
    services = db.query(Service).filter(Service.consultant_id == consultant.id, Service.is_active.is_(True)).all()
    user = _optional_user(request, db)

    if request.method == "GET" and request.query_params.get("change_contact"):
        for key in ("booking_contact_done", "booking_client_name", "booking_client_phone", "booking_client_telegram", "booking_client_email"):
            request.session.pop(key, None)
        return RedirectResponse(f"/book/{calendar_id}/", status_code=302)

    if request.method == "POST":
        form = await request.form()
        if form.get("action") == "client_login":
            login_phone = (form.get("client_phone") or "").strip()
            login_email = (form.get("client_email") or "").strip()
            if not login_phone:
                return templates.TemplateResponse("public_booking.html", page_context(
                    request, db, user, calendar=calendar, services=services,
                    show_client_choice=True, show_contact_form=False, show_booking_form=False,
                    error="Введите номер телефона для входа",
                ))
            conditions = [ClientCard.phone == login_phone]
            if login_email:
                conditions.append(ClientCard.email == login_email)
            card = db.query(ClientCard).filter(ClientCard.consultant_id == consultant.id, or_(*conditions)).first()
            if card:
                request.session.update({
                    "booking_contact_done": True,
                    "booking_client_name": (card.name or "").strip(),
                    "booking_client_phone": (card.phone or login_phone).strip(),
                    "booking_client_telegram": (card.telegram or "").strip(),
                    "booking_client_email": (card.email or login_email).strip(),
                })
                return RedirectResponse(f"/book/{calendar_id}/", status_code=302)
            return templates.TemplateResponse("public_booking.html", page_context(
                request, db, user, calendar=calendar, services=services,
                show_client_choice=False, show_contact_form=True, show_booking_form=False,
                error="Клиент с таким телефоном не найден.",
                contact_phone=login_phone, contact_email=login_email,
            ))
        if form.get("action") == "set_contact":
            client_name = (form.get("client_name") or "").strip()
            client_phone = (form.get("client_phone") or "").strip()
            client_email = (form.get("client_email") or "").strip()
            client_telegram = (form.get("client_telegram") or "").strip().replace(" ", "")
            if not client_phone:
                return templates.TemplateResponse("public_booking.html", page_context(
                    request, db, user, calendar=calendar, services=services,
                    show_booking_form=False, show_client_choice=False, show_contact_form=True,
                    error="Укажите телефон для связи",
                    contact_name=client_name, contact_phone=client_phone,
                    contact_telegram=client_telegram, contact_email=client_email,
                ))
            request.session.update({
                "booking_contact_done": True, "booking_client_name": client_name,
                "booking_client_phone": client_phone, "booking_client_telegram": client_telegram,
                "booking_client_email": client_email,
            })
            return RedirectResponse(f"/book/{calendar_id}/", status_code=302)

        booking, err = create_public_booking(
            db, calendar, int(form.get("service_id")),
            datetime.strptime(form.get("booking_date"), "%Y-%m-%d").date(),
            form.get("booking_time"), form.get("booking_end_time"),
            request.session.get("booking_client_name", "").strip(),
            request.session.get("booking_client_phone", "").strip(),
            request.session.get("booking_client_email", "").strip(),
            (request.session.get("booking_client_telegram") or "").strip().replace(" ", ""),
        )
        if err:
            return templates.TemplateResponse("public_booking.html", page_context(
                request, db, user, calendar=calendar, services=services, show_booking_form=True,
                booking_client_name=request.session.get("booking_client_name", ""),
                booking_client_phone=request.session.get("booking_client_phone", ""),
                booking_client_telegram=request.session.get("booking_client_telegram", ""),
                booking_client_email=request.session.get("booking_client_email", ""),
                error=err,
            ))
        for key in ("booking_contact_done", "booking_client_name", "booking_client_phone", "booking_client_telegram", "booking_client_email"):
            request.session.pop(key, None)
        return templates.TemplateResponse("booking_success.html", page_context(
            request, db, user, booking=booking, service=booking.service,
        ))

    show_booking_form = request.session.get("booking_contact_done") and request.session.get("booking_client_phone")
    step_register = request.query_params.get("step") == "register"
    ctx = {
        "calendar": calendar, "services": services,
        "show_booking_form": bool(show_booking_form),
        "show_client_choice": not show_booking_form and not step_register,
        "show_contact_form": not show_booking_form and step_register,
    }
    if show_booking_form:
        ctx.update({
            "booking_client_name": request.session.get("booking_client_name", ""),
            "booking_client_phone": request.session.get("booking_client_phone", ""),
            "booking_client_telegram": request.session.get("booking_client_telegram", ""),
            "booking_client_email": request.session.get("booking_client_email", ""),
        })
    return templates.TemplateResponse("public_booking.html", page_context(request, db, user, **ctx))


@router.get("/book/{calendar_id}/slots/")
async def available_slots(calendar_id: int, service_id: int, date: str, db: Session = Depends(get_db)):
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.is_active.is_(True)).first()
    if not calendar:
        return JSONResponse({"error": "Календарь не найден"}, status_code=404)
    service = db.query(Service).filter(Service.id == service_id, Service.consultant_id == calendar.consultant_id, Service.is_active.is_(True)).first()
    if not service:
        return JSONResponse({"error": "Услуга не найдена"}, status_code=404)
    result = get_available_slots(db, calendar, service, datetime.strptime(date, "%Y-%m-%d").date())
    return result


@router.get("/booking/")
@router.post("/booking/")
async def specialist_bookings(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    calendars = db.query(Calendar).filter(Calendar.consultant_id == consultant.id).all()
    mark_past_bookings_completed(db, calendars)
    status_filter = request.query_params.get("status", "all")
    if request.method == "POST":
        form = await request.form()
        booking = db.query(Booking).filter(Booking.id == int(form.get("booking_id")), Booking.calendar_id.in_([c.id for c in calendars])).first()
        if booking:
            old_status = booking.status
            if form.get("action") == "confirm":
                booking.status = "confirmed"
            elif form.get("action") == "cancel":
                booking.status = "cancelled"
            db.commit()
            notify_booking_status_changed(db, booking, old_status)
        mark_past_bookings_completed(db, calendars)
    today = date.today()
    now = datetime.now().time()
    cal_ids = [c.id for c in calendars]
    if status_filter == "cancelled":
        upcoming = db.query(Booking).filter(Booking.calendar_id.in_(cal_ids), Booking.status == "cancelled").order_by(Booking.booking_date.desc()).all()
        past = []
    else:
        upcoming = db.query(Booking).filter(Booking.calendar_id.in_(cal_ids), Booking.booking_date >= today, Booking.status != "cancelled").order_by(Booking.booking_date, Booking.booking_time).all()
        past = db.query(Booking).filter(
            Booking.calendar_id.in_(cal_ids),
            or_(Booking.booking_date < today, (Booking.booking_date == today) & (Booking.booking_time < now)),
        ).order_by(Booking.booking_date.desc()).all()
        if status_filter != "all":
            upcoming = [b for b in upcoming if b.status == status_filter]
            past = [b for b in past if b.status == status_filter]
    return templates.TemplateResponse("booking.html", page_context(
        request, db, user, upcoming_bookings=upcoming, past_bookings=past,
        status_filter=status_filter, today=today,
    ))


@router.get("/api/booking/calendar-events/")
async def calendar_events(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    if not user:
        return {"success": False, "events": []}
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
    if not consultant:
        return {"success": False, "events": []}
    year = int(request.query_params.get("year", 0))
    month = int(request.query_params.get("month", 0))
    if not year or not month:
        return {"success": False, "events": []}
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    cal_ids = [c.id for c in db.query(Calendar).filter(Calendar.consultant_id == consultant.id).all()]
    bookings = db.query(Booking).filter(Booking.calendar_id.in_(cal_ids), Booking.booking_date >= start_date, Booking.booking_date <= end_date).order_by(Booking.booking_date, Booking.booking_time).all()
    events = [{
        "id": b.id, "date": b.booking_date.isoformat(),
        "time": b.booking_time.strftime("%H:%M") if b.booking_time else "",
        "end_time": b.booking_end_time.strftime("%H:%M") if b.booking_end_time else "",
        "client_name": b.client_name or "", "client_phone": b.client_phone or "",
        "client_email": b.client_email or "", "client_telegram": b.client_telegram or "",
        "status": b.status, "service": b.service.name if b.service else "",
    } for b in bookings]
    return {"success": True, "events": events}


@router.get("/profile/")
@router.post("/profile/")
async def profile_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if form.get("action") == "update_profile":
            consultant.first_name = form.get("first_name", "")
            consultant.last_name = form.get("last_name", "")
            consultant.middle_name = form.get("middle_name", "")
            consultant.phone = form.get("phone", "")
            consultant.telegram_nickname = form.get("telegram_nickname", "")
            consultant.email = form.get("email", "")
            consultant.profile_description = form.get("profile_description", "")
            consultant.video_link = normalize_url(form.get("video_link"))
            consultant.social_instagram = normalize_url(form.get("social_instagram"))
            consultant.social_facebook = normalize_url(form.get("social_facebook"))
            consultant.social_vk = normalize_url(form.get("social_vk"))
            consultant.social_telegram = normalize_url(form.get("social_telegram"))
            consultant.social_youtube = normalize_url(form.get("social_youtube"))
            consultant.website = normalize_url(form.get("website"))
            try:
                db.commit()
                success = "Профиль успешно обновлен!"
            except Exception as e:
                error = f"Ошибка при обновлении: {e}"
    connected = {sa.provider for sa in db.query(SocialAccount).filter(SocialAccount.user_id == user.id).all()}
    primary = db.query(EmailAddress).filter(EmailAddress.user_id == user.id, EmailAddress.primary.is_(True)).first()
    return templates.TemplateResponse("profile.html", page_context(
        request, db, user, consultant=consultant, success=success, error=error,
        connected_providers=connected, primary_email=primary.email if primary else None,
    ))


@router.get("/clients/")
@router.post("/clients/")
async def client_cards_list(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if form.get("action") == "create":
            db.add(ClientCard(
                consultant_id=consultant.id,
                name=(form.get("name") or "").strip() or None,
                email=(form.get("email") or "").strip() or None,
                phone=(form.get("phone") or "").strip() or None,
                telegram=(form.get("telegram") or "").strip() or None,
                notes=(form.get("notes") or "").strip() or None,
            ))
            db.commit()
            success = "Карточка клиента создана."
        elif form.get("action") == "delete":
            card = db.query(ClientCard).filter(ClientCard.id == int(form.get("card_id")), ClientCard.consultant_id == consultant.id).first()
            if card:
                db.delete(card)
                db.commit()
                success = "Карточка удалена."
    cards = db.query(ClientCard).filter(ClientCard.consultant_id == consultant.id).order_by(ClientCard.updated_at.desc()).all()
    return templates.TemplateResponse("client_cards_list.html", page_context(
        request, db, user, consultant=consultant, cards=cards, success=success, error=error,
    ))


@router.get("/clients/{card_id}/")
@router.post("/clients/{card_id}/")
async def client_card_detail(request: Request, card_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    card = db.query(ClientCard).filter(ClientCard.id == card_id, ClientCard.consultant_id == consultant.id).first()
    if not card:
        return RedirectResponse("/clients/", status_code=302)
    calendars = db.query(Calendar).filter(Calendar.consultant_id == consultant.id).all()
    cal_ids = [c.id for c in calendars]
    history_q = or_(Booking.client_card_id == card.id)
    if card.email:
        history_q = or_(history_q, Booking.client_email == card.email)
    if card.phone:
        history_q = or_(history_q, Booking.client_phone == card.phone)
    if card.telegram:
        t = card.telegram.replace("@", "").strip().split("/")[-1].split("?")[0]
        if t:
            history_q = or_(history_q, Booking.client_telegram.ilike(f"%{t}%"))
    history = db.query(Booking).filter(Booking.calendar_id.in_(cal_ids), history_q).distinct().order_by(Booking.booking_date.desc()).limit(50).all()
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if form.get("action") == "update":
            card.name = (form.get("name") or "").strip() or None
            card.email = (form.get("email") or "").strip() or None
            card.phone = (form.get("phone") or "").strip() or None
            card.telegram = (form.get("telegram") or "").strip() or None
            card.notes = (form.get("notes") or "").strip() or None
            db.commit()
            success = "Изменения сохранены."
        elif form.get("action") == "delete":
            db.delete(card)
            db.commit()
            return RedirectResponse("/clients/", status_code=302)
    total = db.query(Booking).filter(Booking.calendar_id.in_(cal_ids), history_q).distinct().count()
    completed = db.query(Booking).filter(Booking.calendar_id.in_(cal_ids), history_q, Booking.status == "completed").distinct().count()
    return templates.TemplateResponse("client_card_detail.html", page_context(
        request, db, user, consultant=consultant, card=card, history=history,
        total_bookings=total, completed_count=completed, success=success, error=error,
    ))


@router.get("/integrations/")
@router.post("/integrations/")
async def integrations_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    integration = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
    if not integration:
        integration = Integration(consultant_id=consultant.id)
        db.add(integration)
        db.commit()
        db.refresh(integration)
    success = request.session.pop("integrations_success", None)
    error = request.session.pop("integrations_error", None)
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "toggle_telegram":
            integration.telegram_enabled = not integration.telegram_enabled
            db.commit()
            success = "Telegram уведомления включены" if integration.telegram_enabled else "Telegram уведомления отключены"
        elif action == "disconnect_telegram":
            integration.telegram_connected = False
            integration.telegram_bot_token = None
            integration.telegram_chat_id = None
            integration.telegram_link_token = None
            integration.telegram_link_token_created_at = None
            db.commit()
            success = "Telegram отключён."
    return templates.TemplateResponse("integrations.html", page_context(
        request, db, user, integration=integration, success=success, error=error,
    ))


@router.get("/integrations/telegram/connect-app/")
async def connect_telegram_app(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    integration = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
    if not integration:
        integration = Integration(consultant_id=consultant.id)
        db.add(integration)
    integration.telegram_enabled = True
    integration.telegram_link_token = uuid.uuid4().hex
    integration.telegram_link_token_created_at = datetime.utcnow()
    db.commit()
    bot_username = settings.telegram_bot_username.lstrip("@")
    if not bot_username:
        request.session["integrations_error"] = "TELEGRAM_BOT_USERNAME не настроен."
        return RedirectResponse("/integrations/", status_code=302)
    return RedirectResponse(f"https://t.me/{bot_username}?start=connect_spec_{integration.telegram_link_token}", status_code=302)


@router.get("/book/confirm-telegram/{link_token}/")
async def confirm_telegram_browser_page(request: Request, link_token: str, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    if request.query_params.get("telegram") == "confirmed":
        return templates.TemplateResponse("confirm_telegram_browser.html", page_context(
            request, db, user, error=None, success=True, link_token=None,
        ))
    booking = db.query(Booking).filter(Booking.link_token == link_token).first()
    if not booking:
        return templates.TemplateResponse("confirm_telegram_browser.html", page_context(
            request, db, user, error="Ссылка недействительна или уже использована",
            link_token=None, success=False,
        ))
    return templates.TemplateResponse("confirm_telegram_browser.html", page_context(
        request, db, user, link_token=link_token,
        auth_url=str(request.url), success=False, error=None,
    ))
