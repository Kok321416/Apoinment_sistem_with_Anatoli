import os
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
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
from app.services.bookings import (
    create_public_booking,
    mark_past_bookings_completed,
    parse_fio,
    reschedule_booking,
)
from app.services.email_verification import ensure_email_address, resend_verification_email, send_user_verification_email
from app.services.entity_delete import delete_calendar, delete_client_card, delete_service, delete_time_slot
from app.services.slots import get_available_slots
from app.services.telegram import notify_booking_status_changed
from app.templating import guide_context, landing_context, page_context, templates
from app.utils.safe_redirect import login_url_with_next, safe_next_url

router = APIRouter(tags=["pages"])
settings = get_settings()
DAYS_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def _form_csrf_ok(request: Request, form) -> bool:
    token = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
    return validate_csrf_token(request, token)


def _form_int(form, name: str, default: int | None = None) -> int | None:
    raw = form.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_time(raw: str | None):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None


def _save_profile_photo(consultant: Consultant, upload) -> str | None:
    if not upload or not getattr(upload, "filename", None):
        return None
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    ext = Path(upload.filename).suffix.lower()
    if ext not in ALLOWED_PHOTO_EXT:
        return "Допустимы только JPG и PNG"
    raw = upload.file.read(MAX_PHOTO_BYTES + 1)
    if not raw:
        return "Пустой файл изображения"
    if len(raw) > MAX_PHOTO_BYTES:
        return "Файл слишком большой (макс. 5 МБ)"
    try:
        image = Image.open(BytesIO(raw))
        image.load()
    except UnidentifiedImageError:
        return "Файл не является изображением JPG или PNG"
    if image.format not in ("JPEG", "PNG"):
        return "Допустимы только JPG и PNG"
    image = image.convert("RGB")
    w, h = image.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((512, 512), Image.Resampling.LANCZOS)

    dest_dir = settings.media_root / "consultants" / str(consultant.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = "photo.jpg"
    dest_path = dest_dir / filename
    if consultant.profile_photo:
        old = settings.media_root / consultant.profile_photo.lstrip("/")
        if old.is_file():
            old.unlink(missing_ok=True)
    image.save(dest_path, format="JPEG", quality=90, optimize=True)
    consultant.profile_photo = f"consultants/{consultant.id}/{filename}"
    return None


def _optional_user(request: Request, db: Session):
    return get_current_user(request, db)


def _require_user(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None
    return user


def _login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(login_url_with_next(request.url.path), status_code=302)


@router.get("/")
async def landing_page(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    return templates.TemplateResponse("landing/index.html", landing_context(request, db, user))


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    base = settings.site_url.rstrip("/")
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /guide/\n"
        "Allow: /privacy/\n"
        "Allow: /terms/\n"
        "Allow: /book/\n"
        "Disallow: /dashboard/\n"
        "Disallow: /profile/\n"
        "Disallow: /calendars/\n"
        "Disallow: /services/\n"
        "Disallow: /booking/\n"
        "Disallow: /clients/\n"
        "Disallow: /integrations/\n"
        "Disallow: /login/\n"
        "Disallow: /register/\n"
        "Disallow: /accounts/\n"
        "Disallow: /api/\n"
        "Disallow: /media/\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
async def sitemap_xml():
    base = settings.site_url.rstrip("/")
    urls = ["/", "/guide/", "/privacy/", "/terms/", "/login/", "/register/"]
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path in urls:
        body.append(f"  <url><loc>{base}{path}</loc></url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml")


@router.get("/guide/")
async def guide_page(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    return templates.TemplateResponse("landing/guide.html", guide_context(request, db, user))


@router.get("/dashboard/")
async def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
    return templates.TemplateResponse("app/dashboard.html", page_context(request, db, user))


@router.get("/home/")
async def legacy_home_redirect():
    return RedirectResponse("/dashboard/", status_code=301)


@router.get("/privacy/")
@router.get("/terms/")
async def legal_pages(request: Request, db: Session = Depends(get_db)):
    from app.content.legal_copy import (
        PRIVACY_INTRO,
        PRIVACY_SECTIONS,
        TERMS_INTRO,
        TERMS_SECTIONS,
        format_legal_sections,
    )

    user = _optional_user(request, db)
    template = "privacy.html" if request.url.path.startswith("/privacy") else "terms.html"
    brand = settings.site_brand_name
    site = settings.site_url.rstrip("/")
    support = settings.support_email
    telegram = (settings.admin_telegram_username or "").lstrip("@")
    ctx = {
        "brand": brand,
        "site_url": site,
        "support_email": support,
        "telegram": telegram,
    }
    return templates.TemplateResponse(
        template,
        landing_context(
            request,
            db,
            user,
            legal_updated="20.07.2026",
            privacy_intro=PRIVACY_INTRO.format(**ctx),
            privacy_sections=format_legal_sections(PRIVACY_SECTIONS, **ctx),
            terms_intro=TERMS_INTRO.format(**ctx),
            terms_sections=format_legal_sections(TERMS_SECTIONS, **ctx),
        ),
    )


@router.get("/register/")
@router.post("/register/")
async def register_page(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    if user:
        return RedirectResponse("/dashboard/", status_code=302)
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
            return RedirectResponse(f"/accounts/telegram/login/?{urlencode({'process': 'signup', 'next': '/dashboard/'})}", status_code=302)
        else:
            email = (form.get("email") or "").strip()
            password = form.get("password", "")
            password_confirm = form.get("password_confirm", "")
            if not email or not password:
                error = "Укажите почту и пароль"
            elif password != password_confirm:
                error = "Пароли не совпадают"
            elif db.query(User).filter(User.username == email).first():
                error = "Пользователь с такой почтой уже зарегистрирован"
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
                    error = "Не удалось отправить письмо. Проверьте почту или обратитесь к администратору."
                else:
                    return RedirectResponse(
                        f"/accounts/verify-email/?{urlencode({'email': email})}",
                        status_code=302,
                    )
    return templates.TemplateResponse("register.html", page_context(request, db, user, error=error, fio=fio, phone=phone, email=email))


@router.get("/login/")
@router.post("/login/")
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = _optional_user(request, db)
    next_url = safe_next_url(request.query_params.get("next"))
    if user:
        return RedirectResponse(next_url, status_code=302)
    error = success = None
    if request.query_params.get("verified") == "1":
        success = "Почта подтверждена. Теперь можно войти."
    if request.query_params.get("error") == "telegram_expired":
        error = "Ссылка входа через Телеграм истекла. Попробуйте снова."
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
                    error = "Неверная почта или пароль"
                elif not db_user.is_active:
                    error = "Подтвердите почту. Проверьте письмо или отправьте его повторно ниже."
                else:
                    login_user(request, db_user)
                    post_next = safe_next_url(form.get("next") or request.query_params.get("next"))
                    return RedirectResponse(post_next, status_code=302)
    return templates.TemplateResponse("login.html", page_context(
        request, db, user, error=error, success=success,
        resend_email=request.query_params.get("email", ""),
        next_url=next_url,
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
        return _login_redirect(request)
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
            cal_id = _form_int(form, "calendar_id")
            if cal_id is None:
                error = "Некорректный ID календаря"
            else:
                cal = db.query(Calendar).filter(Calendar.id == cal_id, Calendar.consultant_id == consultant.id).first()
                if cal:
                    ok, msg = delete_calendar(db, cal)
                    success, error = (msg, None) if ok else (None, msg)
                else:
                    error = "Календарь не найден"
    calendars = db.query(Calendar).filter(Calendar.consultant_id == consultant.id).order_by(Calendar.name).all()
    slot_counts = {}
    if calendars:
        rows = (
            db.query(TimeSlot.calendar_id, func.count(TimeSlot.id))
            .filter(TimeSlot.calendar_id.in_([c.id for c in calendars]))
            .group_by(TimeSlot.calendar_id)
            .all()
        )
        slot_counts = {calendar_id: count for calendar_id, count in rows}
    for calendar in calendars:
        calendar.time_slots_count = slot_counts.get(calendar.id, 0)
    from app.services.public_client import ensure_public_slug, specialist_public_url

    slug = ensure_public_slug(db, consultant)
    public_url = specialist_public_url(settings.site_url, slug)
    calendars_with_links = [{"calendar": c, "booking_url": f"{public_url}c/{c.id}/"} for c in calendars]
    return templates.TemplateResponse("calendars.html", page_context(
        request, db, user, calendars=calendars, calendars_with_links=calendars_with_links,
        public_booking_url=public_url, success=success, error=error,
    ))


@router.get("/calendars/{calendar_id}/")
@router.post("/calendars/{calendar_id}/")
async def calendar_detail(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
    consultant = get_consultant(db, user)
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id).first()
    if not calendar:
        return RedirectResponse("/calendars/", status_code=302)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "add_time_slot":
            day = _form_int(form, "day_of_week")
            start_t = _parse_time(form.get("start_time"))
            end_t = _parse_time(form.get("end_time"))
            if day is None or start_t is None or end_t is None:
                error = "Заполните день недели и корректное время"
            else:
                db.add(TimeSlot(
                    calendar_id=calendar.id, day_of_week=day,
                    start_time=start_t,
                    end_time=end_t,
                ))
                db.commit()
                success = "Временное окно добавлено!"
        elif action == "delete_time_slot":
            slot_id = _form_int(form, "slot_id")
            slot = (
                db.query(TimeSlot).filter(TimeSlot.id == slot_id, TimeSlot.calendar_id == calendar.id).first()
                if slot_id is not None else None
            )
            if slot:
                ok, msg = delete_time_slot(db, slot)
                success, error = (msg, None) if ok else (None, msg)
            else:
                error = "Временное окно не найдено"
    time_slots_by_day = [
        db.query(TimeSlot).filter(TimeSlot.calendar_id == calendar.id, TimeSlot.day_of_week == d).order_by(TimeSlot.start_time).all()
        for d in range(7)
    ]
    return templates.TemplateResponse("calendar_detail.html", page_context(
        request, db, user, calendar=calendar, time_slots_by_day=time_slots_by_day,
        days_names=DAYS_NAMES, days_short=DAYS_SHORT, success=success, error=error,
    ))


@router.get("/calendars/{calendar_id}/settings/")
@router.post("/calendars/{calendar_id}/settings/")
async def calendar_settings(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
    consultant = get_consultant(db, user)
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id).first()
    if not calendar:
        return RedirectResponse("/calendars/", status_code=302)
    if request.method == "POST":
        form = await request.form()
        calendar.break_between_services_minutes = _form_int(form, "break_between_services_minutes", 0) or 0
        calendar.book_ahead_hours = _form_int(form, "book_ahead_hours", 24) or 24
        calendar.max_services_per_day = _form_int(form, "max_services_per_day", 0) or 0
        calendar.reminder_hours_first = _form_int(form, "reminder_hours_first", 24) or 24
        calendar.reminder_hours_second = _form_int(form, "reminder_hours_second", 1) or 1
        db.commit()
        return RedirectResponse(f"/calendars/{calendar.id}/", status_code=302)
    return templates.TemplateResponse("calendar_settings_edit.html", page_context(request, db, user, calendar=calendar))


@router.get("/services/")
@router.post("/services/")
async def services_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
    consultant = get_consultant(db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "create_service":
            name = form.get("name")
            calendar_id = _form_int(form, "calendar_id")
            calendar = (
                db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id).first()
                if calendar_id is not None else None
            )
            if not name:
                error = "Укажите название услуги"
            elif not calendar:
                error = "Выберите календарь для услуги"
            else:
                db.add(Service(
                    consultant_id=consultant.id,
                    calendar_id=calendar.id,
                    name=name,
                    description=form.get("description", ""),
                    duration_minutes=_form_int(form, "duration_minutes", 60) or 60,
                    price=form.get("price") or None,
                ))
                db.commit()
                success = "Услуга создана успешно!"
        elif action == "toggle_service":
            svc_id = _form_int(form, "service_id")
            svc = (
                db.query(Service).filter(Service.id == svc_id, Service.consultant_id == consultant.id).first()
                if svc_id is not None else None
            )
            if svc:
                svc.is_active = not svc.is_active
                db.commit()
                success = "Статус услуги изменен"
        elif action == "delete_service":
            svc_id = _form_int(form, "service_id")
            svc = (
                db.query(Service).filter(Service.id == svc_id, Service.consultant_id == consultant.id).first()
                if svc_id is not None else None
            )
            if svc:
                ok, msg = delete_service(db, svc)
                success, error = (msg, None) if ok else (None, msg)
            else:
                error = "Услуга не найдена"
    services = db.query(Service).filter(Service.consultant_id == consultant.id).order_by(Service.name).all()
    calendars = db.query(Calendar).filter(Calendar.consultant_id == consultant.id).order_by(Calendar.name).all()
    return templates.TemplateResponse(
        "services.html",
        page_context(request, db, user, services=services, calendars=calendars, success=success, error=error),
    )

@router.get("/book/")
async def book_redirect(db: Session = Depends(get_db)):
    calendar = db.query(Calendar).filter(Calendar.is_active.is_(True)).order_by(Calendar.id).first()
    if not calendar:
        raise HTTPException(status_code=404, detail="Нет доступных календарей")
    consultant = db.query(Consultant).filter(Consultant.id == calendar.consultant_id).first()
    if not consultant:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    from app.services.public_client import ensure_public_slug

    slug = ensure_public_slug(db, consultant)
    return RedirectResponse(f"/s/{slug}/", status_code=302)


@router.get("/book/{calendar_id}/")
@router.post("/book/{calendar_id}/")
async def public_booking(request: Request, calendar_id: int, db: Session = Depends(get_db)):
    """Legacy calendar URL → specialist public flow."""
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.is_active.is_(True)).first()
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")
    consultant = db.query(Consultant).filter(Consultant.id == calendar.consultant_id).first()
    if not consultant:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    from app.services.public_client import ensure_public_slug

    slug = ensure_public_slug(db, consultant)
    return RedirectResponse(f"/s/{slug}/c/{calendar.id}/", status_code=302)


@router.get("/book/{calendar_id}/slots/")
async def available_slots(
    calendar_id: int,
    service_id: int,
    date: str,
    exclude_booking_id: int | None = None,
    db: Session = Depends(get_db),
):
    calendar = db.query(Calendar).filter(Calendar.id == calendar_id, Calendar.is_active.is_(True)).first()
    if not calendar:
        return JSONResponse({"error": "Календарь не найден"}, status_code=404)
    service = db.query(Service).filter(Service.id == service_id, Service.consultant_id == calendar.consultant_id, Service.is_active.is_(True)).first()
    if not service:
        return JSONResponse({"error": "Услуга не найдена"}, status_code=404)
    booking_date = _parse_date(date)
    if not booking_date:
        return JSONResponse({"error": "Некорректная дата"}, status_code=400)
    result = get_available_slots(db, calendar, service, booking_date, exclude_booking_id=exclude_booking_id)
    return result


@router.get("/booking/")
@router.post("/booking/")
async def specialist_bookings(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
    consultant = get_consultant(db, user)
    calendars = db.query(Calendar).filter(Calendar.consultant_id == consultant.id).all()
    mark_past_bookings_completed(db, calendars)
    status_filter = request.query_params.get("status", "all")
    success = error = None
    if request.method == "POST":
        form = await request.form()
        booking_id = _form_int(form, "booking_id")
        booking = (
            db.query(Booking).filter(Booking.id == booking_id, Booking.calendar_id.in_([c.id for c in calendars])).first()
            if booking_id is not None else None
        )
        if booking:
            old_status = booking.status
            action = form.get("action")
            if action == "confirm":
                booking.status = "confirmed"
                db.commit()
                notify_booking_status_changed(db, booking, old_status)
            elif action == "cancel":
                booking.status = "cancelled"
                db.commit()
                notify_booking_status_changed(db, booking, old_status)
            elif action == "complete":
                booking.status = "completed"
                db.commit()
                notify_booking_status_changed(db, booking, old_status)
            elif action == "reschedule":
                new_date = _parse_date(form.get("new_date"))
                new_time = (form.get("new_time") or "").strip()
                if not new_date or not new_time:
                    error = "Укажите новую дату и время"
                else:
                    err = reschedule_booking(db, booking, new_date, new_time)
                    if err:
                        error = err
                    else:
                        success = "Запись перенесена"
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
        status_filter=status_filter, today=today, success=success, error=error,
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
        return _login_redirect(request)
    consultant = get_consultant(db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "disconnect_telegram_login":
            tg_accounts = db.query(SocialAccount).filter(
                SocialAccount.user_id == user.id, SocialAccount.provider == "telegram"
            ).all()
            email_ok = db.query(EmailAddress).filter(
                EmailAddress.user_id == user.id, EmailAddress.verified.is_(True)
            ).first()
            if not tg_accounts:
                error = "Телеграм для входа не привязан."
            elif not user.has_usable_password and not email_ok:
                error = "Нельзя отвязать Телеграм: сначала подтвердите почту или задайте пароль, иначе вход будет недоступен."
            else:
                for acc in tg_accounts:
                    db.delete(acc)
                db.commit()
                success = "Телеграм отвязан. Можно привязать другой аккаунт."
        elif action == "disconnect_email_login":
            rows = db.query(EmailAddress).filter(EmailAddress.user_id == user.id).all()
            has_tg = db.query(SocialAccount).filter(
                SocialAccount.user_id == user.id, SocialAccount.provider == "telegram"
            ).first()
            if not rows or not any(r.verified for r in rows):
                error = "Подтверждённая почта не привязана."
            elif not user.has_usable_password and not has_tg:
                error = "Нельзя отвязать почту: сначала привяжите Телеграм или задайте пароль."
            else:
                for row in rows:
                    row.verified = False
                db.commit()
                success = "Почта отвязана. Можно подтвердить ту же или другую почту заново."
        elif action == "update_profile":
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
            photo_err = _save_profile_photo(consultant, form.get("profile_photo"))
            if photo_err:
                error = photo_err
            else:
                try:
                    from app.services.public_client import ensure_public_slug

                    ensure_public_slug(db, consultant)
                    db.commit()
                    success = "Профиль успешно обновлен!"
                except IntegrityError:
                    db.rollback()
                    error = "Ошибка при обновлении: почта уже используется другим аккаунтом"
                except Exception as e:
                    db.rollback()
                    error = f"Ошибка при обновлении: {e}"
    from app.services.public_client import ensure_public_slug, specialist_public_url

    slug = ensure_public_slug(db, consultant)
    connected = {sa.provider for sa in db.query(SocialAccount).filter(SocialAccount.user_id == user.id).all()}
    primary = db.query(EmailAddress).filter(EmailAddress.user_id == user.id, EmailAddress.primary.is_(True)).first()
    return templates.TemplateResponse("profile.html", page_context(
        request, db, user, consultant=consultant, success=success, error=error,
        connected_providers=connected,
        primary_email=primary.email if primary else consultant.email,
        primary_email_verified=bool(primary and primary.verified),
        public_booking_url=specialist_public_url(settings.site_url, slug),
        has_usable_password=user.has_usable_password,
    ))


@router.get("/clients/")
@router.post("/clients/")
async def client_cards_list(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
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
            card_id = _form_int(form, "card_id")
            card = (
                db.query(ClientCard).filter(ClientCard.id == card_id, ClientCard.consultant_id == consultant.id).first()
                if card_id is not None else None
            )
            if card:
                ok, msg = delete_client_card(db, card)
                success, error = (msg, None) if ok else (None, msg)
            else:
                error = "Карточка не найдена"
    cards = db.query(ClientCard).filter(ClientCard.consultant_id == consultant.id).order_by(ClientCard.updated_at.desc()).all()
    return templates.TemplateResponse("client_cards_list.html", page_context(
        request, db, user, consultant=consultant, cards=cards, success=success, error=error,
    ))


@router.get("/clients/{card_id}/")
@router.post("/clients/{card_id}/")
async def client_card_detail(request: Request, card_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
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
            ok, msg = delete_client_card(db, card)
            if ok:
                return RedirectResponse("/clients/", status_code=302)
            error = msg
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
        return _login_redirect(request)
    consultant = get_consultant(db, user)
    integration = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
    if not integration:
        integration = Integration(consultant_id=consultant.id)
        db.add(integration)
        db.commit()
        db.refresh(integration)
    success = request.session.pop("integrations_success", None)
    error = request.session.pop("integrations_error", None)
    email_pending = request.session.get("integrations_email_pending") or ""
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "toggle_telegram":
            integration.telegram_enabled = not integration.telegram_enabled
            db.commit()
            success = "Уведомления Телеграм включены" if integration.telegram_enabled else "Уведомления Телеграм отключены"
        elif action == "connect_telegram":
            bot_token = (form.get("bot_token") or "").strip()
            chat_id = (form.get("chat_id") or "").strip()
            if not chat_id:
                error = "Укажите идентификатор чата."
            else:
                integration.telegram_chat_id = chat_id
                integration.telegram_bot_token = bot_token or None
                integration.telegram_connected = True
                integration.telegram_enabled = True
                db.commit()
                success = "Телеграм подключён."
        elif action == "disconnect_telegram":
            integration.telegram_connected = False
            integration.telegram_bot_token = None
            integration.telegram_chat_id = None
            integration.telegram_link_token = None
            integration.telegram_link_token_created_at = None
            db.commit()
            success = "Телеграм отключён."
        elif action == "send_email_code":
            from app.services.email import send_verification_email
            from app.services.email_verification import ensure_email_address
            from app.services.public_client import make_email_code

            email = (form.get("email") or consultant.email or user.email or "").strip().lower()
            if not email or "@" not in email:
                error = "Укажите корректную почту."
            else:
                code = make_email_code()
                request.session["integrations_email_code"] = code
                request.session["integrations_email_pending"] = email
                email_pending = email
                ensure_email_address(db, user, email, verified=False)
                consultant.email = email
                user.email = email
                user.username = email
                db.commit()
                if send_verification_email(email, code):
                    success = "Код отправлен на почту. Введите его ниже."
                else:
                    error = "Не удалось отправить письмо. Проверьте SMTP на сервере."
        elif action == "confirm_email_code":
            from app.services.email_verification import ensure_email_address

            email = (form.get("email") or request.session.get("integrations_email_pending") or "").strip().lower()
            code = (form.get("code") or "").strip()
            expected = (request.session.get("integrations_email_code") or "").strip()
            pending = (request.session.get("integrations_email_pending") or "").strip().lower()
            if not expected or email != pending:
                error = "Сначала запросите код на почту."
            elif code != expected:
                error = "Неверный код."
            else:
                ensure_email_address(db, user, email, verified=True)
                consultant.email = email
                user.email = email
                user.username = email
                user.is_active = True
                db.commit()
                request.session.pop("integrations_email_code", None)
                request.session.pop("integrations_email_pending", None)
                email_pending = ""
                success = "Почта подтверждена. Можно входить по почте и паролю."
        elif action == "disconnect_email_login":
            rows = db.query(EmailAddress).filter(EmailAddress.user_id == user.id).all()
            has_tg = db.query(SocialAccount).filter(
                SocialAccount.user_id == user.id, SocialAccount.provider == "telegram"
            ).first()
            if not rows or not any(r.verified for r in rows):
                error = "Подтверждённая почта не привязана."
            elif not user.has_usable_password and not has_tg:
                error = "Нельзя отвязать почту: сначала привяжите Телеграм или задайте пароль."
            else:
                for row in rows:
                    row.verified = False
                db.commit()
                request.session.pop("integrations_email_code", None)
                request.session.pop("integrations_email_pending", None)
                email_pending = ""
                success = "Почта отвязана. Можно привязать заново."
        elif action == "disconnect_telegram_login":
            tg_accounts = db.query(SocialAccount).filter(
                SocialAccount.user_id == user.id, SocialAccount.provider == "telegram"
            ).all()
            email_ok = db.query(EmailAddress).filter(
                EmailAddress.user_id == user.id, EmailAddress.verified.is_(True)
            ).first()
            if not tg_accounts:
                error = "Телеграм для входа не привязан."
            elif not user.has_usable_password and not email_ok:
                error = "Нельзя отвязать Телеграм: сначала подтвердите почту или задайте пароль."
            else:
                for acc in tg_accounts:
                    db.delete(acc)
                db.commit()
                success = "Телеграм для входа отвязан. Можно привязать другой аккаунт."

    primary = db.query(EmailAddress).filter(EmailAddress.user_id == user.id, EmailAddress.primary.is_(True)).first()
    telegram_login_connected = bool(
        db.query(SocialAccount).filter(
            SocialAccount.user_id == user.id, SocialAccount.provider == "telegram"
        ).first()
    )
    return templates.TemplateResponse("integrations.html", page_context(
        request, db, user, integration=integration, success=success, error=error,
        email_address=primary.email if primary else (consultant.email or user.email or ""),
        email_verified=bool(primary and primary.verified),
        email_pending=email_pending,
        telegram_login_connected=telegram_login_connected,
    ))


@router.get("/integrations/telegram/connect-app/")
async def connect_telegram_app(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return _login_redirect(request)
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
