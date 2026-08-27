import logging
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from sqlalchemy import and_, or_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.auth.passwords import hash_password, verify_password
from app.auth.session import logout_user
from app.config import get_settings
from app.database import get_async_db
from app.deps import get_consultant, normalize_phone, normalize_url, require_specialist_mode, require_specialist_mode_async
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
    parse_fio,
)
from app.services.login_methods import can_disconnect_social, can_disconnect_social_async
from app.services.entity_delete import (
    delete_calendar,
    delete_calendar_async,
    delete_client_card,
    delete_client_card_async,
    delete_service,
    delete_service_async,
    delete_time_slot,
    delete_time_slot_async,
)
from app.services.slots import get_available_slots_async
from app.templating import (
    apps_context_async,
    guide_context_async,
    landing_context_async,
    media_relative_path,
    page_context_async,
    templates,
)
from app.utils.safe_redirect import login_url_with_next, safe_next_url

router = APIRouter(tags=["pages"])
settings = get_settings()
logger = logging.getLogger(__name__)
DAYS_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
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


async def _read_upload_bytes(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if data:
        return data
    if upload.file:
        upload.file.seek(0)
        return upload.file.read(limit + 1)
    return b""


async def _save_profile_photo(consultant: Consultant, upload) -> str | None:
    if not upload or not isinstance(upload, UploadFile):
        return None
    filename = (upload.filename or "").strip()
    if not filename:
        return None
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PHOTO_EXT:
        return "Допустимы только JPG и PNG"
    raw = await _read_upload_bytes(upload, MAX_PHOTO_BYTES)
    if not raw:
        return "Пустой файл изображения"
    if len(raw) > MAX_PHOTO_BYTES:
        return "Файл слишком большой (макс. 5 МБ)"
    try:
        image = Image.open(BytesIO(raw))
        image.load()
    except UnidentifiedImageError:
        return "Файл не является изображением JPG или PNG"
    if image.format not in ("JPEG", "PNG", "WEBP"):
        return "Допустимы только JPG, PNG и WEBP"
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
        old = settings.media_root / media_relative_path(consultant.profile_photo)
        if old.is_file():
            old.unlink(missing_ok=True)
    image.save(dest_path, format="JPEG", quality=90, optimize=True)
    consultant.profile_photo = f"consultants/{consultant.id}/{filename}"
    return None


async def _async_session_if_logged_in(request: Request):
    """Open async DB only when cookie session has user_id (public pages fast path)."""
    from app.auth.session import get_current_user_async, get_session_user_id
    from app.database import _ensure_async_engine

    if "session" not in request.scope or not get_session_user_id(request):
        return None, None
    db = _ensure_async_engine()()
    user = await get_current_user_async(request, db)
    return db, user


async def _require_user_async(request: Request, db):
    from app.auth.session import get_current_user_async

    return await get_current_user_async(request, db)


def _login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(login_url_with_next(request.url.path), status_code=302)


@router.get("/")
async def landing_page(request: Request):
    """Public landing: skip MySQL when guest (no session user) for faster TTFB."""
    db, user = await _async_session_if_logged_in(request)
    try:
        return templates.TemplateResponse(
            "landing/index.html",
            await landing_context_async(request, db, user),
        )
    finally:
        if db is not None:
            await db.close()


@router.get("/tg/")
async def telegram_mini_app_entry(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Landing for Telegram Mini App (Menu Button / web_app buttons)."""
    from app.auth.session import get_current_user_async
    from app.services.active_mode import (
        MODE_CLIENT,
        MODE_SPECIALIST,
        VALID_MODES,
        get_active_mode_async,
        set_active_mode,
        user_has_consultant_async,
    )

    user = await get_current_user_async(request, db)
    mode_q = (request.query_params.get("mode") or "").strip().lower()
    has_c = bool(user and await user_has_consultant_async(db, user.id))
    if user and mode_q in VALID_MODES:
        set_active_mode(request, mode_q, has_consultant=has_c)
    active = await get_active_mode_async(request, db, user.id) if user else MODE_CLIENT
    return templates.TemplateResponse(
        "public/tg_mini_app.html",
        await page_context_async(
            request,
            db,
            user,
            tg_hub=True,
            load_telegram_webapp=True,
            tg_mode=active,
            tg_has_consultant=has_c,
            tg_show_mode_switcher=has_c,
            tg_mode_client=MODE_CLIENT,
            tg_mode_specialist=MODE_SPECIALIST,
        ),
    )


@router.get("/tg/apps/")
async def telegram_mini_app_apps_guide(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Install / phone guide inside Mini App shell (avoids full landing chrome)."""
    from app.auth.session import get_current_user_async
    from app.content.apps_copy import APPS_PAGE

    user = await get_current_user_async(request, db)
    return templates.TemplateResponse(
        "public/tg_apps.html",
        await page_context_async(
            request,
            db,
            user,
            tg_hub=True,
            load_telegram_webapp=True,
            apps_page=APPS_PAGE,
        ),
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    base = settings.site_url.rstrip("/")
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /guide/\n"
        "Allow: /apps/\n"
        "Allow: /privacy/\n"
        "Allow: /terms/\n"
        "Allow: /book/\n"
        "Allow: /tg/\n"
        "Allow: /tg/apps/\n"
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
    urls = ["/", "/guide/", "/apps/", "/privacy/", "/terms/", "/login/", "/register/", "/book/"]
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path in urls:
        body.append(f"  <url><loc>{base}{path}</loc></url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml")


@router.get("/guide/")
async def guide_page(request: Request):
    db, user = await _async_session_if_logged_in(request)
    try:
        return templates.TemplateResponse(
            "landing/guide.html",
            await guide_context_async(request, db, user),
        )
    finally:
        if db is not None:
            await db.close()


@router.get("/apps/")
async def apps_page(request: Request):
    """How to install / use on Android (RuStore soon) and iPhone (Mini App + PWA)."""
    db, user = await _async_session_if_logged_in(request)
    try:
        return templates.TemplateResponse(
            "landing/apps.html",
            await apps_context_async(request, db, user),
        )
    finally:
        if db is not None:
            await db.close()


@router.get("/dashboard/")
async def dashboard_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    from app.services.active_mode import MODE_SPECIALIST, get_active_mode_async, user_has_consultant_async

    has_c = await user_has_consultant_async(db, user.id)
    mode = await get_active_mode_async(request, db, user.id)
    need_mode = request.query_params.get("need_mode") == "specialist"
    ctx = await page_context_async(
        request,
        db,
        user,
        need_mode_specialist=need_mode,
    )
    if has_c and mode == MODE_SPECIALIST:
        from app.services.clients_crm import build_crm_payload_async

        consultant = (
            await db.execute(select(Consultant).where(Consultant.user_id == user.id))
        ).scalar_one_or_none()
        if consultant:
            cards = list(
                (
                    await db.execute(
                        select(ClientCard)
                        .where(ClientCard.consultant_id == consultant.id)
                        .order_by(ClientCard.updated_at.desc(), ClientCard.id.desc())
                    )
                )
                .scalars()
                .all()
            )
            crm = await build_crm_payload_async(db, consultant.id, cards)
            ctx.update(
                {
                    "dash_kpi": crm["dashboard"],
                    "dash_recent_clients": crm["clients"][:8],
                    "dash_activity": crm["activity"],
                }
            )
        else:
            ctx.update(
                {
                    "dash_kpi": {
                        "total": 0,
                        "new_count": 0,
                        "today_bookings": 0,
                        "upcoming": 0,
                    },
                    "dash_recent_clients": [],
                    "dash_activity": [],
                }
            )
        return templates.TemplateResponse("app/dashboard.html", ctx)
    return templates.TemplateResponse("app/dashboard_client.html", ctx)


@router.post("/account/mode/")
async def set_account_mode(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    from app.services.active_mode import set_active_mode, user_has_consultant_async

    form = await request.form()
    if not _form_csrf_ok(request, form):
        return RedirectResponse("/dashboard/", status_code=302)
    mode = (form.get("mode") or "").strip()
    set_active_mode(
        request,
        mode,
        has_consultant=await user_has_consultant_async(db, user.id),
    )
    next_url = safe_next_url(form.get("next") or request.query_params.get("next") or "/dashboard/")
    return RedirectResponse(next_url, status_code=302)


@router.get("/my-bookings/")
async def my_bookings_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from sqlalchemy.orm import selectinload

    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    from app.services.active_mode import (
        MODE_CLIENT,
        list_client_bookings_async,
        set_active_mode,
        user_has_consultant_async,
    )

    set_active_mode(
        request,
        MODE_CLIENT,
        has_consultant=await user_has_consultant_async(db, user.id),
    )
    bookings = await list_client_bookings_async(db, user.id)
    if bookings:
        bookings = list(
            (
                await db.execute(
                    select(Booking)
                    .options(
                        selectinload(Booking.service),
                        selectinload(Booking.calendar).selectinload(Calendar.consultant),
                    )
                    .where(Booking.id.in_([b.id for b in bookings]))
                    .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
    return templates.TemplateResponse(
        "app/my_bookings.html",
        await page_context_async(request, db, user, bookings=bookings),
    )


@router.get("/home/")
async def legacy_home_redirect():
    return RedirectResponse("/dashboard/", status_code=301)


@router.get("/privacy/")
@router.get("/terms/")
async def legal_pages(request: Request):
    from app.content.legal_copy import (
        PRIVACY_INTRO,
        PRIVACY_SECTIONS,
        TERMS_INTRO,
        TERMS_SECTIONS,
        format_legal_sections,
    )

    db, user = await _async_session_if_logged_in(request)
    try:
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
            await landing_context_async(
                request,
                db,
                user,
                legal_updated="23.07.2026",
                privacy_intro=PRIVACY_INTRO.format(**ctx),
                privacy_sections=format_legal_sections(PRIVACY_SECTIONS, **ctx),
                terms_intro=TERMS_INTRO.format(**ctx),
                terms_sections=format_legal_sections(TERMS_SECTIONS, **ctx),
            ),
        )
    finally:
        if db is not None:
            await db.close()


@router.get("/register/")
@router.post("/register/")
async def register_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.session import get_current_user_async
    from app.services.client_channel import normalize_client_channel, with_client_query
    from app.services.consultant_onboarding import (
        apply_user_names_from_fio,
        create_consultant_for_user_async,
    )
    from app.services.email_verification import (
        ensure_email_address_async,
        send_user_verification_email_async,
    )

    user = await get_current_user_async(request, db)
    client_channel = normalize_client_channel(request.query_params.get("client"))
    if user:
        next_after = safe_next_url(request.query_params.get("next"), default="/dashboard/")
        return RedirectResponse(next_after, status_code=302)
    error = fio = phone = email = None
    accept_privacy = False
    account_role = (request.query_params.get("as") or "specialist").strip().lower()
    if account_role not in ("client", "specialist"):
        account_role = "specialist"
    register_errors = {
        "yandex_signup": "Сначала укажите ФИО и телефон, затем выберите Яндекс.",
        "yandex_failed": "Не удалось завершить регистрацию через Яндекс. Попробуйте снова или выберите другой способ входа.",
        "vk_signup": "Сначала укажите ФИО и телефон, затем выберите VK.",
        "vk_failed": "Не удалось завершить регистрацию через VK. Попробуйте снова или выберите другой способ входа.",
    }
    if request.query_params.get("error") in register_errors:
        error = register_errors[request.query_params.get("error")]
    if request.method == "POST":
        form = await request.form()
        fio = (form.get("fio") or "").strip()
        phone = normalize_phone(form.get("phone"))
        accept_privacy = form.get("accept_privacy") == "1"
        auth_method = form.get("auth_method", "email")
        client_channel = normalize_client_channel(form.get("client") or request.query_params.get("client"))
        account_role = (form.get("account_role") or "specialist").strip().lower()
        if account_role not in ("client", "specialist"):
            account_role = "specialist"
        if settings.force_consultant_on_signup:
            account_role = "specialist"
        as_specialist = account_role == "specialist"
        tg_process = "signup" if as_specialist else "signup_client"
        ya_process = "signup" if as_specialist else "signup_client"
        vk_process = "signup" if as_specialist else "signup_client"
        next_after = safe_next_url(form.get("next") or request.query_params.get("next"), default="/dashboard/")
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
        elif form.get("accept_privacy") != "1":
            error = "Нужно принять политику конфиденциальности и условия использования."
        elif not fio or not phone:
            error = "Укажите ФИО и номер телефона"
        elif auth_method == "yandex":
            from app.services.yandex_auth import yandex_oauth_configured
            if not yandex_oauth_configured():
                error = "Вход через Яндекс не настроен на сервере."
            else:
                request.session["register_fio"] = fio
                request.session["register_phone"] = phone
                request.session["register_accepted_legal"] = True
                return RedirectResponse(
                    with_client_query(
                        f"/accounts/yandex/login/?{urlencode({'process': ya_process, 'next': next_after})}",
                        client_channel,
                    ),
                    status_code=302,
                )
        elif auth_method == "vk":
            from app.services.vk_auth import vk_oauth_configured
            if not vk_oauth_configured():
                error = "Вход через VK не настроен на сервере."
            else:
                request.session["register_fio"] = fio
                request.session["register_phone"] = phone
                request.session["register_accepted_legal"] = True
                return RedirectResponse(
                    with_client_query(
                        f"/accounts/vk/login/?{urlencode({'process': vk_process, 'next': next_after})}",
                        client_channel,
                    ),
                    status_code=302,
                )
        elif auth_method == "telegram":
            request.session["register_fio"] = fio
            request.session["register_phone"] = phone
            request.session["register_accepted_legal"] = True
            return RedirectResponse(
                with_client_query(
                    f"/accounts/telegram/login/?{urlencode({'process': tg_process, 'next': next_after})}",
                    client_channel,
                ),
                status_code=302,
            )
        else:
            email = (form.get("email") or "").strip().lower()
            password = form.get("password", "")
            password_confirm = form.get("password_confirm", "")
            if not email or not password:
                error = "Укажите почту и пароль"
            elif password != password_confirm:
                error = "Пароли не совпадают"
            elif (await db.execute(select(User).where(User.username == email))).scalar_one_or_none():
                error = "Пользователь с такой почтой уже зарегистрирован"
            elif as_specialist and (
                await db.execute(select(Consultant).where(Consultant.email == email))
            ).scalar_one_or_none():
                error = "Эта почта уже используется другим специалистом"
            else:
                try:
                    first_name, last_name, _middle = parse_fio(fio)
                    new_user = User(
                        username=email,
                        email=email,
                        password=hash_password(password),
                        first_name=first_name or "",
                        last_name=last_name or "",
                        is_active=False,
                        date_joined=datetime.utcnow(),
                    )
                    db.add(new_user)
                    await db.flush()
                    if as_specialist:
                        await create_consultant_for_user_async(
                            db, new_user, fio=fio, phone=phone, email=email
                        )
                    else:
                        apply_user_names_from_fio(new_user, fio)
                    await ensure_email_address_async(db, new_user, email, verified=False)
                    request.session["register_phone"] = phone
                    if not await send_user_verification_email_async(db, new_user):
                        await db.rollback()
                        error = "Не удалось отправить письмо. Проверьте почту или обратитесь к администратору."
                    else:
                        verify_q = {"email": email}
                        if next_after and next_after != "/dashboard/":
                            verify_q["next"] = next_after
                        return RedirectResponse(
                            f"/accounts/verify-email/?{urlencode(verify_q)}",
                            status_code=302,
                        )
                except IntegrityError:
                    await db.rollback()
                    error = "Пользователь с такой почтой уже зарегистрирован"
                except Exception:
                    logger.exception("Email registration failed for %s", email)
                    await db.rollback()
                    error = "Не удалось завершить регистрацию. Попробуйте позже или выберите другой способ входа."
    return templates.TemplateResponse(
        "register.html",
        await page_context_async(
            request,
            db,
            user,
            error=error,
            fio=fio or "",
            phone=phone or "",
            email=email or "",
            account_role=account_role,
            accept_privacy=accept_privacy,
            next_url=safe_next_url(request.query_params.get("next"), default=""),
            client_channel=client_channel,
        ),
    )


@router.get("/become-specialist/")
@router.post("/become-specialist/")
async def become_specialist_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    from app.services.consultant_onboarding import (
        create_consultant_for_user_async,
        find_consultant_for_user_async,
    )

    if await find_consultant_for_user_async(db, user.id):
        return RedirectResponse("/dashboard/", status_code=302)
    error = None
    fio = f"{user.last_name or ''} {user.first_name or ''}".strip()
    phone = ""
    if request.method == "POST":
        form = await request.form()
        fio = (form.get("fio") or "").strip()
        phone = normalize_phone(form.get("phone"))
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
        elif not fio or not phone:
            error = "Укажите ФИО и номер телефона"
        else:
            try:
                await create_consultant_for_user_async(
                    db, user, fio=fio, phone=phone, email=user.email or None
                )
                await db.commit()
                if "session" in request.scope:
                    request.session["has_consultant"] = True
                    request.session["active_mode"] = "specialist"
                return RedirectResponse("/dashboard/", status_code=302)
            except IntegrityError:
                await db.rollback()
                error = "Не удалось создать профиль специалиста. Возможно, почта уже занята."
            except Exception:
                logger.exception("become-specialist failed for user %s", user.id)
                await db.rollback()
                error = "Не удалось создать профиль. Попробуйте позже."
    return templates.TemplateResponse(
        "app/become_specialist.html",
        await page_context_async(request, db, user, error=error, fio=fio, phone=phone),
    )


@router.get("/login/")
@router.post("/login/")
async def login_page(request: Request):
    from app.auth.login_flow import finish_login_async
    from app.auth.session import get_current_user_async
    from app.database import _ensure_async_engine
    from app.services.email_verification import resend_verification_email_async

    needs_db = request.method == "POST" or (
        "session" in request.scope and request.session.get("user_id")
    )
    db = _ensure_async_engine()() if needs_db else None
    try:
        user = await get_current_user_async(request, db) if db is not None else None
        next_url = safe_next_url(request.query_params.get("next"))
        if user:
            return RedirectResponse(next_url, status_code=302)
        error = success = None
        if request.query_params.get("verified") == "1":
            success = "Почта подтверждена. Теперь можно войти."
        if request.query_params.get("success") == "password_reset":
            success = "Пароль обновлён. Войдите с новым паролем."
        if request.query_params.get("error") == "telegram_expired":
            error = "Ссылка входа через Телеграм истекла. Попробуйте снова."
        yandex_errors = {
            "yandex_denied": "Вход через Яндекс отменён.",
            "yandex_config": "Вход через Яндекс не настроен на сервере.",
            "yandex_state": "Ошибка безопасности при входе через Яндекс. Попробуйте снова.",
            "yandex_token": "Не удалось получить токен Яндекса. Попробуйте снова.",
            "yandex_profile": "Не удалось получить профиль Яндекса.",
            "yandex_failed": "Не удалось войти через Яндекс. Зарегистрируйтесь или используйте другой способ входа.",
        }
        vk_errors = {
            "vk_denied": "Вход через VK отменён.",
            "vk_config": "Вход через VK не настроен на сервере.",
            "vk_state": "Ошибка безопасности при входе через VK. Попробуйте снова.",
            "vk_token": "Не удалось получить токен VK. Попробуйте снова.",
            "vk_profile": "Не удалось получить профиль VK.",
            "vk_failed": "Не удалось войти через VK. Зарегистрируйтесь или используйте другой способ входа.",
        }
        if request.query_params.get("error") in yandex_errors:
            error = yandex_errors[request.query_params.get("error")]
        elif request.query_params.get("error") in vk_errors:
            error = vk_errors[request.query_params.get("error")]
        if request.method == "POST":
            assert db is not None
            form = await request.form()
            if not _form_csrf_ok(request, form):
                error = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
            elif form.get("action") == "resend_verification":
                email_resend = form.get("email", "")
                ok, msg = await resend_verification_email_async(db, email_resend)
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
                    from app.security.request_guards import client_ip
                    from app.services.rate_limit import check_rate_limit

                    ip = client_ip(request)
                    if not check_rate_limit(f"login:{ip}", max_calls=15, window_sec=300):
                        error = "Слишком много попыток входа. Подождите несколько минут."
                    else:
                        db_user = (
                            await db.execute(select(User).where(User.username == email))
                        ).scalar_one_or_none()
                        if not db_user or not verify_password(password, db_user.password):
                            error = "Неверная почта или пароль"
                            try:
                                from app.services.admin_audit import write_admin_audit

                                write_admin_audit(
                                    db,
                                    actor_user_id=None,
                                    action="login_failed",
                                    entity="user",
                                    entity_id=str(db_user.id) if db_user else None,
                                    payload={"email": (email or "")[:120]},
                                    request=request,
                                )
                                await db.commit()
                            except Exception:
                                try:
                                    await db.rollback()
                                except Exception:
                                    pass
                        elif not db_user.is_active:
                            error = "Подтвердите почту. Проверьте письмо или отправьте его повторно ниже."
                        else:
                            post_next = safe_next_url(form.get("next") or request.query_params.get("next"))
                            return await finish_login_async(request, db_user, db, post_next)
        return templates.TemplateResponse(
            "login.html",
            await page_context_async(
                request,
                db,
                user,
                error=error,
                success=success,
                resend_email=request.query_params.get("email", ""),
                next_url=next_url,
            ),
        )
    finally:
        if db is not None:
            await db.close()


@router.get("/login/2fa/")
@router.post("/login/2fa/")
async def login_2fa_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.login_flow import verify_login_2fa_async
    from app.auth.session import get_current_user_async, login_user_async
    from app.security.request_guards import client_ip
    from app.services.rate_limit import check_rate_limit

    pending_id = request.session.get("pending_2fa_user_id")
    if not pending_id:
        return RedirectResponse("/login/", status_code=302)
    if await get_current_user_async(request, db):
        return RedirectResponse(safe_next_url(request.query_params.get("next")), status_code=302)

    error = None
    next_url = safe_next_url(request.query_params.get("next") or request.session.get("pending_2fa_next"))
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности (CSRF). Обновите страницу."
        else:
            ip = client_ip(request)
            if not check_rate_limit(f"login-2fa:{ip}", max_calls=20, window_sec=300):
                error = "Слишком много попыток. Подождите несколько минут."
            else:
                code = (form.get("code") or "").strip()
                db_user = await db.get(User, int(pending_id))
                if not db_user or not await verify_login_2fa_async(db, db_user, code):
                    error = "Неверный код"
                else:
                    request.session.pop("pending_2fa_user_id", None)
                    request.session.pop("pending_2fa_next", None)
                    await login_user_async(request, db_user, db)
                    post_next = safe_next_url(form.get("next") or next_url)
                    return RedirectResponse(post_next, status_code=302)

    return templates.TemplateResponse(
        "login_2fa.html",
        await page_context_async(request, db, None, error=error, next_url=next_url),
    )


@router.get("/support/")
@router.post("/support/")
async def support_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.session import get_current_user_async
    from app.services.platform_support import create_support_ticket_async

    user = await get_current_user_async(request, db)
    success = error = None
    form_name = form_email = form_subject = form_body = ""
    if user:
        form_email = user.email or user.username
        form_name = user.get_full_name()
    if request.method == "POST":
        form = await request.form()
        form_name = (form.get("contact_name") or "").strip()
        form_email = (form.get("contact_email") or "").strip()
        form_subject = (form.get("subject") or "").strip()
        form_body = (form.get("body") or "").strip()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу."
        else:
            ticket, err = await create_support_ticket_async(
                db,
                subject=form_subject,
                body=form_body,
                contact_email=form_email,
                contact_name=form_name,
                user_id=user.id if user else None,
            )
            if err:
                error = err
            else:
                success = f"Обращение #{ticket.id} принято. Ответ придёт на {form_email}."
                form_subject = form_body = ""
    return templates.TemplateResponse(
        "support.html",
        await page_context_async(
            request,
            db,
            user,
            success=success,
            error=error,
            form_name=form_name,
            form_email=form_email,
            form_subject=form_subject,
            form_body=form_body,
        ),
    )


@router.post("/logout/")
async def logout_page(request: Request):
    form = await request.form()
    if _form_csrf_ok(request, form):
        logout_user(request)
        return RedirectResponse("/", status_code=302)
    # CSRF failed: do not clear session (avoid forged logout), stay in cabinet
    return RedirectResponse("/dashboard/", status_code=302)


@router.get("/manage/")
async def manage_hub_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    from app.services.calendars_hub import build_calendars_payload_async
    from app.services.public_client import ensure_public_slug_async, specialist_public_url
    from app.services.services_catalog import build_catalog_payload_async

    calendars = list(
        (
            await db.execute(
                select(Calendar)
                .where(Calendar.consultant_id == consultant.id)
                .order_by(Calendar.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    services = list(
        (
            await db.execute(
                select(Service)
                .where(Service.consultant_id == consultant.id)
                .order_by(Service.sort_order, Service.name)
            )
        )
        .scalars()
        .all()
    )
    slug = await ensure_public_slug_async(db, consultant)
    public_url = specialist_public_url(settings.site_url, slug)
    cal_hub = await build_calendars_payload_async(db, calendars, public_url)
    svc_hub = await build_catalog_payload_async(db, consultant.id)
    return templates.TemplateResponse(
        "manage_hub.html",
        await page_context_async(
            request,
            db,
            user,
            calendars=calendars,
            services=services,
            hub_calendars=cal_hub["calendars"],
            hub_cal_dashboard=cal_hub["dashboard"],
            hub_services=svc_hub.get("services") or [],
            hub_svc_dashboard=svc_hub.get("dashboard") or {},
            success=request.query_params.get("success"),
            error=request.query_params.get("error"),
        ),
    )


@router.get("/calendars/")
@router.post("/calendars/")
async def calendars_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    if request.method == "GET":
        return RedirectResponse("/manage/#calendars", status_code=302)
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        else:
            action = form.get("action")
            if action == "create_calendar":
                name = form.get("name")
                color = form.get("color", "#667eea")
                if name:
                    db.add(Calendar(consultant_id=consultant.id, name=name, color=color))
                    await db.commit()
                    success = "Календарь создан успешно!"
                else:
                    error = "Укажите название календаря"
            elif action == "toggle_calendar":
                cal_id = _form_int(form, "calendar_id")
                cal = None
                if cal_id is not None:
                    cal = (
                        await db.execute(
                            select(Calendar).where(
                                Calendar.id == cal_id,
                                Calendar.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                if cal:
                    cal.is_active = not cal.is_active
                    await db.commit()
                    success = "Статус календаря изменён"
                else:
                    error = "Календарь не найден"
            elif action == "update_calendar":
                cal_id = _form_int(form, "calendar_id")
                cal = None
                if cal_id is not None:
                    cal = (
                        await db.execute(
                            select(Calendar).where(
                                Calendar.id == cal_id,
                                Calendar.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                name = (form.get("name") or "").strip()
                color = form.get("color") or "#667eea"
                if not cal:
                    error = "Календарь не найден"
                elif not name:
                    error = "Укажите название календаря"
                else:
                    cal.name = name
                    cal.color = color
                    await db.commit()
                    success = "Календарь обновлён"
            elif action == "delete_calendar":
                cal_id = _form_int(form, "calendar_id")
                if cal_id is None:
                    error = "Некорректный ID календаря"
                else:
                    cal = (
                        await db.execute(
                            select(Calendar).where(
                                Calendar.id == cal_id,
                                Calendar.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if cal:
                        ok, msg = await delete_calendar_async(db, cal)
                        success, error = (msg, None) if ok else (None, msg)
                    else:
                        error = "Календарь не найден"
    if success:
        from app.services.response_cache import invalidate_consultant

        invalidate_consultant(consultant.id)
        return RedirectResponse(
            "/manage/?success=" + quote(success) + "#calendars",
            status_code=302,
        )
    if error:
        return RedirectResponse(
            "/manage/?error=" + quote(error) + "#calendars",
            status_code=302,
        )
    return RedirectResponse("/manage/#calendars", status_code=302)


@router.get("/calendars/{calendar_id}/")
@router.post("/calendars/{calendar_id}/")
async def calendar_detail(request: Request, calendar_id: int, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not calendar:
        return RedirectResponse("/calendars/", status_code=302)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        else:
            action = form.get("action")
            if action == "add_time_slot":
                day = _form_int(form, "day_of_week")
                start_t = _parse_time(form.get("start_time"))
                end_t = _parse_time(form.get("end_time"))
                if day is None or start_t is None or end_t is None:
                    error = "Заполните день недели и корректное время"
                else:
                    db.add(
                        TimeSlot(
                            calendar_id=calendar.id,
                            day_of_week=day,
                            start_time=start_t,
                            end_time=end_t,
                        )
                    )
                    await db.commit()
                    success = "Временное окно добавлено!"
            elif action == "update_time_slot":
                slot_id = _form_int(form, "slot_id")
                start_t = _parse_time(form.get("start_time"))
                end_t = _parse_time(form.get("end_time"))
                slot = None
                if slot_id is not None:
                    slot = (
                        await db.execute(
                            select(TimeSlot).where(
                                TimeSlot.id == slot_id,
                                TimeSlot.calendar_id == calendar.id,
                            )
                        )
                    ).scalar_one_or_none()
                if not slot or start_t is None or end_t is None:
                    error = "Некорректные данные окна"
                elif start_t >= end_t:
                    error = "Время начала должно быть раньше окончания"
                else:
                    slot.start_time = start_t
                    slot.end_time = end_t
                    await db.commit()
                    success = "Окно обновлено"
            elif action == "delete_time_slot":
                slot_id = _form_int(form, "slot_id")
                slot = None
                if slot_id is not None:
                    slot = (
                        await db.execute(
                            select(TimeSlot).where(
                                TimeSlot.id == slot_id,
                                TimeSlot.calendar_id == calendar.id,
                            )
                        )
                    ).scalar_one_or_none()
                if slot:
                    ok, msg = await delete_time_slot_async(db, slot)
                    success, error = (msg, None) if ok else (None, msg)
                else:
                    error = "Временное окно не найдено"
    if success:
        from app.services.response_cache import invalidate_calendar

        invalidate_calendar(calendar.id, consultant_id=consultant.id)
    from app.services.public_client import ensure_public_slug_async, specialist_public_url

    slug = await ensure_public_slug_async(db, consultant)
    booking_url = f"{specialist_public_url(settings.site_url, slug)}c/{calendar.id}/"
    return templates.TemplateResponse(
        "calendar_detail.html",
        await page_context_async(
            request,
            db,
            user,
            calendar=calendar,
            booking_url=booking_url,
            days_names=DAYS_NAMES,
            days_short=DAYS_SHORT,
            success=success,
            error=error,
        ),
    )


@router.get("/calendars/{calendar_id}/settings/")
@router.post("/calendars/{calendar_id}/settings/")
async def calendar_settings(request: Request, calendar_id: int, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not calendar:
        return RedirectResponse("/calendars/", status_code=302)
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            return templates.TemplateResponse(
                "calendar_settings_edit.html",
                await page_context_async(
                    request,
                    db,
                    user,
                    calendar=calendar,
                    error="Ошибка безопасности. Обновите страницу.",
                ),
            )
        calendar.break_between_services_minutes = _form_int(form, "break_between_services_minutes", 0) or 0
        calendar.book_ahead_hours = _form_int(form, "book_ahead_hours", 24) or 24
        calendar.max_services_per_day = _form_int(form, "max_services_per_day", 0) or 0
        calendar.reminder_hours_first = _form_int(form, "reminder_hours_first", 24) or 24
        calendar.reminder_hours_second = _form_int(form, "reminder_hours_second", 1) or 1
        await db.commit()
        from app.services.response_cache import invalidate_calendar

        invalidate_calendar(calendar.id, consultant_id=consultant.id)
        return RedirectResponse(f"/calendars/{calendar.id}/", status_code=302)
    return templates.TemplateResponse(
        "calendar_settings_edit.html",
        await page_context_async(request, db, user, calendar=calendar),
    )


@router.get("/services/")
@router.post("/services/")
async def services_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    if request.method == "GET":
        if request.query_params.get("legacy") == "1":
            user = await _require_user_async(request, db)
            if not user:
                return _login_redirect(request)
            await require_specialist_mode_async(request, db, user)
            return templates.TemplateResponse(
                "services.html",
                await page_context_async(request, db, user),
            )
        return RedirectResponse("/manage/#services", status_code=302)
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        else:
            action = form.get("action")
            if action == "create_service":
                name = form.get("name")
                calendar_id = _form_int(form, "calendar_id")
                calendar = None
                if calendar_id is not None:
                    calendar = (
                        await db.execute(
                            select(Calendar).where(
                                Calendar.id == calendar_id,
                                Calendar.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                if not name:
                    error = "Укажите название услуги"
                elif not calendar:
                    error = "Выберите календарь для услуги"
                else:
                    db.add(
                        Service(
                            consultant_id=consultant.id,
                            calendar_id=calendar.id,
                            name=name,
                            description=form.get("description", ""),
                            duration_minutes=_form_int(form, "duration_minutes", 60) or 60,
                            price=form.get("price") or None,
                        )
                    )
                    await db.commit()
                    success = "Услуга создана успешно!"
            elif action == "update_service":
                svc_id = _form_int(form, "service_id")
                svc = None
                if svc_id is not None:
                    svc = (
                        await db.execute(
                            select(Service).where(
                                Service.id == svc_id,
                                Service.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                calendar_id = _form_int(form, "calendar_id")
                calendar = None
                if calendar_id is not None:
                    calendar = (
                        await db.execute(
                            select(Calendar).where(
                                Calendar.id == calendar_id,
                                Calendar.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                name = (form.get("name") or "").strip()
                if not svc:
                    error = "Услуга не найдена"
                elif not name:
                    error = "Укажите название услуги"
                elif not calendar:
                    error = "Выберите календарь"
                else:
                    svc.name = name
                    svc.description = form.get("description") or ""
                    svc.duration_minutes = _form_int(form, "duration_minutes", 60) or 60
                    svc.price = form.get("price") or None
                    svc.calendar_id = calendar.id
                    await db.commit()
                    success = "Услуга обновлена"
            elif action == "toggle_service":
                svc_id = _form_int(form, "service_id")
                svc = None
                if svc_id is not None:
                    svc = (
                        await db.execute(
                            select(Service).where(
                                Service.id == svc_id,
                                Service.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                if svc:
                    svc.is_active = not svc.is_active
                    await db.commit()
                    success = "Статус услуги изменен"
            elif action == "delete_service":
                svc_id = _form_int(form, "service_id")
                svc = None
                if svc_id is not None:
                    svc = (
                        await db.execute(
                            select(Service).where(
                                Service.id == svc_id,
                                Service.consultant_id == consultant.id,
                            )
                        )
                    ).scalar_one_or_none()
                if svc:
                    ok, msg = await delete_service_async(db, svc)
                    success, error = (msg, None) if ok else (None, msg)
                else:
                    error = "Услуга не найдена"
    if success:
        from app.services.response_cache import invalidate_consultant

        invalidate_consultant(consultant.id)
        return RedirectResponse(
            "/manage/?success=" + quote(success) + "#services",
            status_code=302,
        )
    if error:
        return RedirectResponse(
            "/manage/?error=" + quote(error) + "#services",
            status_code=302,
        )
    return RedirectResponse("/manage/#services", status_code=302)


@router.get("/book/")
async def book_redirect(db: AsyncSession = Depends(get_async_db)):
    calendar = (
        await db.execute(
            select(Calendar).where(Calendar.is_active.is_(True)).order_by(Calendar.id)
        )
    ).scalars().first()
    if not calendar:
        raise HTTPException(status_code=404, detail="Нет доступных календарей")
    consultant = (
        await db.execute(select(Consultant).where(Consultant.id == calendar.consultant_id))
    ).scalar_one_or_none()
    if not consultant:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    from app.services.public_client import ensure_public_slug_async

    slug = await ensure_public_slug_async(db, consultant)
    return RedirectResponse(f"/s/{slug}/", status_code=302)


@router.get("/book/{calendar_id}/")
@router.post("/book/{calendar_id}/")
async def public_booking(request: Request, calendar_id: int, db: AsyncSession = Depends(get_async_db)):
    """Legacy calendar URL → specialist public flow."""
    calendar = (
        await db.execute(
            select(Calendar).where(Calendar.id == calendar_id, Calendar.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")
    consultant = (
        await db.execute(select(Consultant).where(Consultant.id == calendar.consultant_id))
    ).scalar_one_or_none()
    if not consultant:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    from app.services.public_client import ensure_public_slug_async

    slug = await ensure_public_slug_async(db, consultant)
    return RedirectResponse(f"/s/{slug}/c/{calendar.id}/", status_code=302)


@router.get("/book/{calendar_id}/slots/")
async def available_slots(
    request: Request,
    calendar_id: int,
    service_id: int,
    date: str,
    exclude_booking_id: int | None = None,
    db: AsyncSession = Depends(get_async_db),
):
    from app.auth.session import get_current_user_async

    user = await get_current_user_async(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    calendar = (
        await db.execute(
            select(Calendar).where(Calendar.id == calendar_id, Calendar.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if not calendar:
        return JSONResponse({"error": "Календарь не найден"}, status_code=404)
    consultant = (
        await db.execute(select(Consultant).where(Consultant.user_id == user.id))
    ).scalar_one_or_none()
    if not consultant or calendar.consultant_id != consultant.id:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    service = (
        await db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.consultant_id == calendar.consultant_id,
                Service.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not service:
        return JSONResponse({"error": "Услуга не найдена"}, status_code=404)
    booking_date = _parse_date(date)
    if not booking_date:
        return JSONResponse({"error": "Некорректная дата"}, status_code=400)
    return await get_available_slots_async(
        db, calendar, service, booking_date, exclude_booking_id=exclude_booking_id
    )


@router.get("/booking/")
@router.post("/booking/")
async def specialist_bookings(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.session import get_current_user_async
    from app.deps import require_specialist_mode_async
    from app.services.bookings import mark_past_bookings_completed_async
    from app.services.bookings_hub import build_bookings_payload_async
    from sqlalchemy.orm import selectinload

    user = await get_current_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    calendars = list(
        (await db.execute(select(Calendar).where(Calendar.consultant_id == consultant.id))).scalars().all()
    )
    cal_ids = [c.id for c in calendars]
    if cal_ids:
        await mark_past_bookings_completed_async(db, calendars)
    status_filter = request.query_params.get("status", "all")
    success = error = None

    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        else:
            booking_id = _form_int(form, "booking_id")
            booking = None
            if booking_id is not None and cal_ids:
                booking = (
                    await db.execute(
                        select(Booking)
                        .options(selectinload(Booking.service), selectinload(Booking.calendar))
                        .where(Booking.id == booking_id, Booking.calendar_id.in_(cal_ids))
                    )
                ).scalar_one_or_none()
            if booking:
                old_status = booking.status
                action = form.get("action")
                if action == "confirm":
                    booking.status = "confirmed"
                    await db.commit()
                    from app.services.notify_bridge import schedule_status_changed

                    schedule_status_changed(booking.id, old_status)
                elif action == "cancel":
                    booking.status = "cancelled"
                    await db.commit()
                    from app.services.notify_bridge import schedule_status_changed

                    schedule_status_changed(booking.id, old_status)
                elif action == "complete":
                    booking.status = "completed"
                    await db.commit()
                    from app.services.notify_bridge import schedule_status_changed

                    schedule_status_changed(booking.id, old_status)
                elif action == "reschedule":
                    new_date = _parse_date(form.get("new_date"))
                    new_time = (form.get("new_time") or "").strip()
                    if not new_date or not new_time:
                        error = "Укажите новую дату и время"
                    else:
                        from app.services.bookings import reschedule_booking_async

                        err = await reschedule_booking_async(db, booking, new_date, new_time)
                        if err:
                            error = err
                        else:
                            success = "Запись перенесена"
        if cal_ids:
            await mark_past_bookings_completed_async(db, calendars)

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(get_settings().timezone or "Europe/Moscow")
    now_dt = datetime.now(tz)
    today = now_dt.date()
    now = now_dt.time()
    booking_opts = (selectinload(Booking.service), selectinload(Booking.calendar))
    if not cal_ids:
        upcoming = []
        past = []
    elif status_filter == "cancelled":
        upcoming = list(
            (
                await db.execute(
                    select(Booking)
                    .options(*booking_opts)
                    .where(Booking.calendar_id.in_(cal_ids), Booking.status == "cancelled")
                    .order_by(Booking.booking_date.desc())
                )
            ).scalars().unique().all()
        )
        past = []
    else:
        upcoming = list(
            (
                await db.execute(
                    select(Booking)
                    .options(*booking_opts)
                    .where(
                        Booking.calendar_id.in_(cal_ids),
                        Booking.status.in_(["pending", "confirmed"]),
                        or_(
                            Booking.booking_date > today,
                            and_(Booking.booking_date == today, Booking.booking_time >= now),
                            and_(Booking.status == "pending", Booking.booking_date >= today),
                        ),
                    )
                    .order_by(Booking.booking_date, Booking.booking_time)
                )
            ).scalars().unique().all()
        )
        past = list(
            (
                await db.execute(
                    select(Booking)
                    .options(*booking_opts)
                    .where(
                        Booking.calendar_id.in_(cal_ids),
                        or_(
                            Booking.booking_date < today,
                            and_(
                                Booking.booking_date == today,
                                Booking.booking_time < now,
                                Booking.status != "pending",
                            ),
                        ),
                    )
                    .order_by(Booking.booking_date.desc())
                )
            ).scalars().unique().all()
        )
        if status_filter != "all":
            upcoming = [b for b in upcoming if b.status == status_filter]
            past = [b for b in past if b.status == status_filter]

    hub_payload = await build_bookings_payload_async(db, cal_ids, upcoming, past, today, now)

    return templates.TemplateResponse(
        "booking.html",
        await page_context_async(
            request,
            db,
            user,
            upcoming_bookings=upcoming,
            past_bookings=past,
            status_filter=status_filter,
            today=today,
            hub_dashboard=hub_payload["dashboard"],
            hub_upcoming_groups=hub_payload["upcoming_groups"],
            hub_past_groups=hub_payload["past_groups"],
            hub_sidebar=hub_payload["sidebar"],
            hub_payload=hub_payload,
            success=success,
            error=error,
        ),
    )

@router.get("/api/booking/calendar-events/")
async def calendar_events(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.session import get_current_user_async
    from sqlalchemy.orm import selectinload

    user = await get_current_user_async(request, db)
    if not user:
        return {"success": False, "events": []}
    consultant = (
        await db.execute(select(Consultant).where(Consultant.user_id == user.id))
    ).scalar_one_or_none()
    if not consultant:
        return {"success": False, "events": []}
    try:
        year = int(request.query_params.get("year", 0))
        month = int(request.query_params.get("month", 0))
    except (TypeError, ValueError):
        return {"success": False, "events": []}
    if not year or not (1 <= month <= 12):
        return {"success": False, "events": []}
    from calendar import monthrange

    try:
        _, last_day = monthrange(year, month)
    except ValueError:
        return {"success": False, "events": []}
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    cal_ids = list(
        (
            await db.execute(select(Calendar.id).where(Calendar.consultant_id == consultant.id))
        )
        .scalars()
        .all()
    )
    if not cal_ids:
        return {"success": True, "events": []}
    bookings = list(
        (
            await db.execute(
                select(Booking)
                .options(selectinload(Booking.service))
                .where(
                    Booking.calendar_id.in_(cal_ids),
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                )
                .order_by(Booking.booking_date, Booking.booking_time)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    events = [
        {
            "id": b.id,
            "date": b.booking_date.isoformat(),
            "time": b.booking_time.strftime("%H:%M") if b.booking_time else "",
            "end_time": b.booking_end_time.strftime("%H:%M") if b.booking_end_time else "",
            "client_name": b.client_name or "",
            "client_phone": b.client_phone or "",
            "client_email": b.client_email or "",
            "client_telegram": b.client_telegram or "",
            "status": b.status,
            "service": b.service.name if b.service else "",
        }
        for b in bookings
    ]
    return {"success": True, "events": events}


@router.get("/profile/")
@router.post("/profile/")
async def profile_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from sqlalchemy.orm import selectinload

    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    # Reload with category for specialization() without lazy IO
    consultant = (
        await db.execute(
            select(Consultant)
            .options(selectinload(Consultant.category))
            .where(Consultant.id == consultant.id)
        )
    ).scalar_one()
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        else:
            action = form.get("action")
            if action == "disconnect_telegram_login":
                ok, msg = await can_disconnect_social_async(db, user, "telegram")
                if not ok:
                    error = msg
                else:
                    rows = list(
                        (
                            await db.execute(
                                select(SocialAccount).where(
                                    SocialAccount.user_id == user.id,
                                    SocialAccount.provider == "telegram",
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for acc in rows:
                        await db.delete(acc)
                    await db.commit()
                    success = "Телеграм отвязан. Можно привязать другой аккаунт."
            elif action == "disconnect_yandex_login":
                ok, msg = await can_disconnect_social_async(db, user, "yandex")
                if not ok:
                    error = msg
                else:
                    rows = list(
                        (
                            await db.execute(
                                select(SocialAccount).where(
                                    SocialAccount.user_id == user.id,
                                    SocialAccount.provider == "yandex",
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for acc in rows:
                        await db.delete(acc)
                    await db.commit()
                    success = "Яндекс отвязан. Можно привязать другой аккаунт."
            elif action == "disconnect_vk_login":
                ok, msg = await can_disconnect_social_async(db, user, "vk")
                if not ok:
                    error = msg
                else:
                    rows = list(
                        (
                            await db.execute(
                                select(SocialAccount).where(
                                    SocialAccount.user_id == user.id,
                                    SocialAccount.provider == "vk",
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for acc in rows:
                        await db.delete(acc)
                    await db.commit()
                    success = "VK отвязан. Можно привязать другой аккаунт."
            elif action == "disconnect_email_login":
                rows = list(
                    (
                        await db.execute(select(EmailAddress).where(EmailAddress.user_id == user.id))
                    )
                    .scalars()
                    .all()
                )
                has_social = (
                    await db.execute(
                        select(SocialAccount.id).where(
                            SocialAccount.user_id == user.id,
                            SocialAccount.provider.in_(("telegram", "yandex", "vk")),
                        ).limit(1)
                    )
                ).first()
                if not rows or not any(r.verified for r in rows):
                    error = "Подтверждённая почта не привязана."
                elif not user.has_usable_password and not has_social:
                    error = "Нельзя отвязать почту: сначала привяжите Телеграм, Яндекс, VK или задайте пароль."
                else:
                    for row in rows:
                        row.verified = False
                    await db.commit()
                    success = "Почта отвязана. Можно подтвердить ту же или другую почту заново."
            elif action == "enable_2fa":
                from app.services.specialist_totp import enable_specialist_2fa_async

                ok, msg = await enable_specialist_2fa_async(db, user, (form.get("code") or "").strip())
                if ok:
                    success = msg
                else:
                    error = msg
            elif action == "disable_2fa":
                from app.services.specialist_totp import disable_specialist_2fa_async

                ok, msg = await disable_specialist_2fa_async(db, user, (form.get("code") or "").strip())
                if ok:
                    success = msg
                else:
                    error = msg
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
                photo_err = await _save_profile_photo(consultant, form.get("profile_photo"))
                if photo_err:
                    error = photo_err
                else:
                    try:
                        from app.services.public_client import ensure_public_slug_async

                        await ensure_public_slug_async(db, consultant)
                        await db.commit()
                        success = "Профиль успешно обновлен!"
                    except IntegrityError:
                        await db.rollback()
                        error = "Ошибка при обновлении: почта уже используется другим аккаунтом"
                    except Exception as e:
                        await db.rollback()
                        error = f"Ошибка при обновлении: {e}"
    if success:
        from app.services.response_cache import invalidate_profile
        from app.templating import clear_header_cache

        invalidate_profile(consultant.id, user.id)
        clear_header_cache(request)
    from app.services.public_client import ensure_public_slug_async, specialist_public_url
    from app.services.profile_hub import build_profile_payload_async, completion_meta_async, completeness_async, dashboard_stats_async
    from app.services.yandex_auth import yandex_oauth_configured

    slug = await ensure_public_slug_async(db, consultant)
    connected = {
        sa.provider
        for sa in (
            await db.execute(select(SocialAccount).where(SocialAccount.user_id == user.id))
        ).scalars().all()
    }
    primary = (
        await db.execute(
            select(EmailAddress).where(
                EmailAddress.user_id == user.id,
                EmailAddress.primary.is_(True),
            )
        )
    ).scalar_one_or_none()
    profile_completeness = await completeness_async(consultant, db, consultant.id)
    profile_dashboard = await dashboard_stats_async(db, consultant.id)
    profile_dashboard["completeness"] = profile_completeness["percent"]
    profile_initial_data = await build_profile_payload_async(
        db,
        consultant,
        user,
        connected_providers=connected,
        primary_email=primary.email if primary else consultant.email,
        primary_email_verified=bool(primary and primary.verified),
        has_usable_password=user.has_usable_password,
        yandex_oauth_enabled=yandex_oauth_configured(),
    )
    profile_photo_url = profile_initial_data["profile"].get("photo_url")
    profile_initials = (
        (consultant.first_name or consultant.last_name or "?")[:1].upper()
    )
    from app.services.specialist_totp import specialist_2fa_enabled_async, specialist_2fa_provisioning_async

    totp_enabled = await specialist_2fa_enabled_async(db, user.id)
    totp_secret = totp_uri = None
    if not totp_enabled:
        totp_secret, totp_uri = await specialist_2fa_provisioning_async(db, user)
    return templates.TemplateResponse(
        "profile.html",
        await page_context_async(
            request,
            db,
            user,
            consultant=consultant,
            success=success,
            error=error,
            connected_providers=connected,
            primary_email=primary.email if primary else consultant.email,
            primary_email_verified=bool(primary and primary.verified),
            public_booking_url=specialist_public_url(settings.site_url, slug),
            has_usable_password=user.has_usable_password,
            profile_completeness=profile_completeness,
            profile_dashboard=profile_dashboard,
            profile_completion_meta=await completion_meta_async(consultant, db, consultant.id),
            profile_initial_data=profile_initial_data,
            profile_photo_url=profile_photo_url,
            profile_initials=profile_initials,
            specialist_2fa_enabled=totp_enabled,
            specialist_2fa_secret=totp_secret,
            specialist_2fa_uri=totp_uri,
        ),
    )


@router.get("/clients/")
@router.post("/clients/")
async def client_cards_list(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        elif form.get("action") == "create":
            db.add(
                ClientCard(
                    consultant_id=consultant.id,
                    name=(form.get("name") or "").strip() or None,
                    email=(form.get("email") or "").strip() or None,
                    phone=(form.get("phone") or "").strip() or None,
                    telegram=(form.get("telegram") or "").strip() or None,
                    notes=(form.get("notes") or "").strip() or None,
                )
            )
            await db.commit()
            success = "Карточка клиента создана."
        elif form.get("action") == "delete":
            card_id = _form_int(form, "card_id")
            card = None
            if card_id is not None:
                card = (
                    await db.execute(
                        select(ClientCard).where(
                            ClientCard.id == card_id,
                            ClientCard.consultant_id == consultant.id,
                        )
                    )
                ).scalar_one_or_none()
            if card:
                ok, msg = await delete_client_card_async(db, card)
                success, error = (msg, None) if ok else (None, msg)
            else:
                error = "Карточка не найдена"
    cards = list(
        (
            await db.execute(
                select(ClientCard)
                .where(ClientCard.consultant_id == consultant.id)
                .order_by(ClientCard.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    from app.services.clients_crm import build_crm_payload_async

    crm_payload = await build_crm_payload_async(db, consultant.id, cards)
    return templates.TemplateResponse(
        "client_cards_list.html",
        await page_context_async(
            request,
            db,
            user,
            consultant=consultant,
            cards=cards,
            success=success,
            error=error,
            crm_dashboard=crm_payload["dashboard"],
            crm_clients=crm_payload["clients"],
            crm_activity=crm_payload["activity"],
            crm_payload=crm_payload,
        ),
    )


@router.get("/clients/{card_id}/")
@router.post("/clients/{card_id}/")
async def client_card_detail(request: Request, card_id: int, db: AsyncSession = Depends(get_async_db)):
    from sqlalchemy import func

    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    card = (
        await db.execute(
            select(ClientCard).where(
                ClientCard.id == card_id,
                ClientCard.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not card:
        return RedirectResponse("/clients/", status_code=302)
    cal_ids = list(
        (
            await db.execute(select(Calendar.id).where(Calendar.consultant_id == consultant.id))
        )
        .scalars()
        .all()
    )
    history_q = or_(Booking.client_card_id == card.id)
    if card.email:
        history_q = or_(history_q, Booking.client_email == card.email)
    if card.phone:
        history_q = or_(history_q, Booking.client_phone == card.phone)
    if card.telegram:
        t = card.telegram.replace("@", "").strip().split("/")[-1].split("?")[0]
        if t:
            history_q = or_(history_q, Booking.client_telegram.ilike(f"%{t}%"))
    from sqlalchemy.orm import selectinload

    if cal_ids:
        history = list(
            (
                await db.execute(
                    select(Booking)
                    .options(selectinload(Booking.service), selectinload(Booking.calendar))
                    .where(Booking.calendar_id.in_(cal_ids), history_q)
                    .distinct()
                    .order_by(Booking.booking_date.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    else:
        history = []
    success = error = None
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
        elif form.get("action") == "update":
            if "name" in form:
                card.name = (form.get("name") or "").strip() or None
            if "email" in form:
                card.email = (form.get("email") or "").strip() or None
            if "phone" in form:
                card.phone = (form.get("phone") or "").strip() or None
            if "telegram" in form:
                card.telegram = (form.get("telegram") or "").strip() or None
            if "notes" in form:
                card.notes = (form.get("notes") or "").strip() or None
            await db.commit()
            success = "Изменения сохранены."
        elif form.get("action") == "delete":
            ok, msg = await delete_client_card_async(db, card)
            if ok:
                return RedirectResponse("/clients/", status_code=302)
            error = msg
    if cal_ids:
        total = (
            await db.execute(
                select(func.count()).select_from(
                    select(Booking.id)
                    .where(Booking.calendar_id.in_(cal_ids), history_q)
                    .distinct()
                    .subquery()
                )
            )
        ).scalar_one()
        completed = (
            await db.execute(
                select(func.count()).select_from(
                    select(Booking.id)
                    .where(
                        Booking.calendar_id.in_(cal_ids),
                        history_q,
                        Booking.status == "completed",
                    )
                    .distinct()
                    .subquery()
                )
            )
        ).scalar_one()
    else:
        total = 0
        completed = 0

    from datetime import date as date_cls

    from app.services.clients_crm import booking_stats_async, serialize_card
    from app.services.diagnostics_service import attempt_to_view, list_attempts_for_card
    from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature

    stats = await booking_stats_async(db, consultant.id, [card.id])
    crm_client = serialize_card(card, stats, date_cls.today())
    today = date_cls.today()
    upcoming_bookings = [
        b
        for b in history
        if b.booking_date and b.booking_date >= today and b.status in ("pending", "confirmed")
    ][:5]

    diagnostic_results = []
    if consultant_has_feature(consultant, FEATURE_DIAGNOSTICS):
        diagnostic_results = [
            attempt_to_view(a)
            for a in await list_attempts_for_card(
                db, consultant_id=consultant.id, client_card_id=card.id
            )
        ]

    return templates.TemplateResponse(
        "client_card_detail.html",
        await page_context_async(
            request,
            db,
            user,
            consultant=consultant,
            card=card,
            history=history,
            upcoming_bookings=upcoming_bookings,
            crm_client=crm_client,
            total_bookings=total,
            completed_count=completed,
            success=success,
            error=error,
            diagnostic_results=diagnostic_results,
            show_diagnostics=bool(diagnostic_results is not None and consultant_has_feature(consultant, FEATURE_DIAGNOSTICS)),
        ),
    )


@router.get("/integrations/")
@router.post("/integrations/")
async def integrations_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    integration = (
        await db.execute(select(Integration).where(Integration.consultant_id == consultant.id))
    ).scalar_one_or_none()
    if not integration:
        integration = Integration(consultant_id=consultant.id)
        db.add(integration)
        await db.commit()
        await db.refresh(integration)
    success = request.session.pop("integrations_success", None)
    error = request.session.pop("integrations_error", None)
    email_pending = request.session.get("integrations_email_pending") or ""
    if request.method == "POST":
        form = await request.form()
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
            action = None
        else:
            action = form.get("action")
        if action == "toggle_telegram":
            integration.telegram_enabled = not integration.telegram_enabled
            await db.commit()
            success = "Уведомления Телеграм включены" if integration.telegram_enabled else "Уведомления Телеграм отключены"
        elif action == "connect_telegram":
            from app.services.integration_telegram import claim_integration_telegram_chat_async

            bot_token = (form.get("bot_token") or "").strip()
            chat_id = (form.get("chat_id") or "").strip()
            if not chat_id:
                error = "Укажите идентификатор чата."
            else:
                ok, err = await claim_integration_telegram_chat_async(
                    db,
                    integration,
                    chat_id,
                    bot_token=bot_token or None,
                    source="integrations_form",
                    actor_user_id=user.id if user else None,
                )
                if not ok:
                    error = err
                else:
                    await db.commit()
                    success = "Телеграм подключён."
        elif action == "disconnect_telegram":
            from app.services.integration_telegram import clear_integration_telegram_chat_async

            await clear_integration_telegram_chat_async(
                db,
                integration,
                source="integrations_disconnect",
                actor_user_id=user.id if user else None,
            )
            await db.commit()
            success = "Телеграм отключён."
        elif action == "send_email_code":
            from app.services.email import send_verification_email
            from app.services.email_verification import ensure_email_address_async
            from app.services.public_client import make_email_code

            email = (form.get("email") or consultant.email or user.email or "").strip().lower()
            if not email or "@" not in email:
                error = "Укажите корректную почту."
            else:
                existing = (
                    await db.execute(
                        select(User).where(User.username == email, User.id != user.id)
                    )
                ).scalar_one_or_none()
                if existing:
                    error = "Эта почта уже используется другим аккаунтом."
                else:
                    code = make_email_code()
                    request.session["integrations_email_code"] = code
                    request.session["integrations_email_pending"] = email
                    await ensure_email_address_async(db, user, email, verified=False)
                    consultant.email = email
                    db_user = await db.get(User, user.id)
                    if db_user:
                        db_user.email = email
                        db_user.username = email
                    try:
                        await db.commit()
                    except IntegrityError:
                        await db.rollback()
                        error = "Эта почта уже используется другим аккаунтом."
                    else:
                        if send_verification_email(email, code):
                            request.session["integrations_success"] = (
                                f"Код отправлен на {email}. Введите его ниже, чтобы завершить привязку."
                            )
                            return RedirectResponse("/integrations/", status_code=302)
                        error = "Не удалось отправить письмо. Проверьте SMTP на сервере."
        elif action == "confirm_email_code":
            from app.services.email import send_email_link_success_email
            from app.services.email_verification import ensure_email_address_async

            email = (form.get("email") or request.session.get("integrations_email_pending") or "").strip().lower()
            code = (form.get("code") or "").strip().replace(" ", "")
            expected = (request.session.get("integrations_email_code") or "").strip()
            pending = (request.session.get("integrations_email_pending") or "").strip().lower()
            if not expected or email != pending:
                error = "Сначала запросите код на почту."
            elif code != expected:
                error = "Неверный код."
            else:
                await ensure_email_address_async(db, user, email, verified=True)
                consultant.email = email
                db_user = await db.get(User, user.id)
                if db_user:
                    db_user.email = email
                    db_user.username = email
                    db_user.is_active = True
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                    error = "Эта почта уже используется другим аккаунтом."
                else:
                    request.session.pop("integrations_email_code", None)
                    request.session.pop("integrations_email_pending", None)
                    needs_password = not user.has_usable_password
                    if not send_email_link_success_email(email, needs_password=needs_password):
                        logger.warning("Failed to send email link success message to %s", email)
                    request.session["integrations_success"] = (
                        "Спасибо, что привязали почту. Теперь вы можете авторизовываться через почту."
                    )
                    return RedirectResponse("/integrations/", status_code=302)
        elif action == "disconnect_email_login":
            rows = list(
                (await db.execute(select(EmailAddress).where(EmailAddress.user_id == user.id))).scalars().all()
            )
            has_social = (
                await db.execute(
                    select(SocialAccount.id).where(
                        SocialAccount.user_id == user.id,
                        SocialAccount.provider.in_(("telegram", "yandex", "vk")),
                    ).limit(1)
                )
            ).first()
            if not rows or not any(r.verified for r in rows):
                error = "Подтверждённая почта не привязана."
            elif not user.has_usable_password and not has_social:
                error = "Нельзя отвязать почту: сначала привяжите Телеграм, Яндекс, VK или задайте пароль."
            else:
                for row in rows:
                    row.verified = False
                await db.commit()
                request.session.pop("integrations_email_code", None)
                request.session.pop("integrations_email_pending", None)
                email_pending = ""
                success = "Почта отвязана. Можно привязать заново."
        elif action == "disconnect_telegram_login":
            ok, msg = await can_disconnect_social_async(db, user, "telegram")
            if not ok:
                error = msg
            else:
                for acc in list(
                    (
                        await db.execute(
                            select(SocialAccount).where(
                                SocialAccount.user_id == user.id,
                                SocialAccount.provider == "telegram",
                            )
                        )
                    )
                    .scalars()
                    .all()
                ):
                    await db.delete(acc)
                await db.commit()
                success = "Телеграм для входа отвязан. Можно привязать другой аккаунт."
        elif action == "disconnect_yandex_login":
            ok, msg = await can_disconnect_social_async(db, user, "yandex")
            if not ok:
                error = msg
            else:
                for acc in list(
                    (
                        await db.execute(
                            select(SocialAccount).where(
                                SocialAccount.user_id == user.id,
                                SocialAccount.provider == "yandex",
                            )
                        )
                    )
                    .scalars()
                    .all()
                ):
                    await db.delete(acc)
                await db.commit()
                success = "Яндекс для входа отвязан. Можно привязать другой аккаунт."
        elif action == "disconnect_vk_login":
            ok, msg = await can_disconnect_social_async(db, user, "vk")
            if not ok:
                error = msg
            else:
                for acc in list(
                    (
                        await db.execute(
                            select(SocialAccount).where(
                                SocialAccount.user_id == user.id,
                                SocialAccount.provider == "vk",
                            )
                        )
                    )
                    .scalars()
                    .all()
                ):
                    await db.delete(acc)
                await db.commit()
                success = "VK для входа отвязан. Можно привязать другой аккаунт."

    primary = (
        await db.execute(
            select(EmailAddress).where(
                EmailAddress.user_id == user.id,
                EmailAddress.primary.is_(True),
            )
        )
    ).scalar_one_or_none()
    telegram_login_connected = bool(
        (
            await db.execute(
                select(SocialAccount.id).where(
                    SocialAccount.user_id == user.id,
                    SocialAccount.provider == "telegram",
                ).limit(1)
            )
        ).first()
    )
    yandex_login_connected = bool(
        (
            await db.execute(
                select(SocialAccount.id).where(
                    SocialAccount.user_id == user.id,
                    SocialAccount.provider == "yandex",
                ).limit(1)
            )
        ).first()
    )
    vk_login_connected = bool(
        (
            await db.execute(
                select(SocialAccount.id).where(
                    SocialAccount.user_id == user.id,
                    SocialAccount.provider == "vk",
                ).limit(1)
            )
        ).first()
    )
    from app.services.yandex_auth import yandex_oauth_configured
    from app.services.vk_auth import vk_oauth_configured

    return templates.TemplateResponse(
        "integrations.html",
        await page_context_async(
            request,
            db,
            user,
            integration=integration,
            success=success,
            error=error,
            email_address=primary.email if primary else (consultant.email or user.email or ""),
            email_verified=bool(primary and primary.verified),
            email_pending=email_pending,
            telegram_login_connected=telegram_login_connected,
            yandex_login_connected=yandex_login_connected,
            vk_login_connected=vk_login_connected,
            yandex_oauth_enabled=yandex_oauth_configured(),
            vk_oauth_enabled=vk_oauth_configured(),
        ),
    )


@router.get("/integrations/telegram/connect-app/")
async def connect_telegram_app(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user_async(request, db)
    if not user:
        return _login_redirect(request)
    consultant = await require_specialist_mode_async(request, db, user)
    integration = (
        await db.execute(select(Integration).where(Integration.consultant_id == consultant.id))
    ).scalar_one_or_none()
    if not integration:
        integration = Integration(consultant_id=consultant.id)
        db.add(integration)
    integration.telegram_enabled = True
    integration.telegram_link_token = uuid.uuid4().hex
    integration.telegram_link_token_created_at = datetime.utcnow()
    await db.commit()
    bot_username = settings.telegram_bot_username.lstrip("@")
    if not bot_username:
        request.session["integrations_error"] = "TELEGRAM_BOT_USERNAME не настроен."
        return RedirectResponse("/integrations/", status_code=302)
    return RedirectResponse(
        f"https://t.me/{bot_username}?start=connect_spec_{integration.telegram_link_token}",
        status_code=302,
    )


@router.get("/book/confirm-telegram/{link_token}/")
async def confirm_telegram_browser_page(
    request: Request, link_token: str, db: AsyncSession = Depends(get_async_db)
):
    from app.auth.session import get_current_user_async

    user = await get_current_user_async(request, db)
    if request.query_params.get("telegram") == "confirmed":
        return templates.TemplateResponse(
            "confirm_telegram_browser.html",
            await page_context_async(
                request, db, user, error=None, success=True, link_token=None,
            ),
        )
    booking = (
        await db.execute(select(Booking).where(Booking.link_token == link_token))
    ).scalar_one_or_none()
    if not booking:
        return templates.TemplateResponse(
            "confirm_telegram_browser.html",
            await page_context_async(
                request,
                db,
                user,
                error="Ссылка недействительна или уже использована",
                link_token=None,
                success=False,
            ),
        )
    return templates.TemplateResponse(
        "confirm_telegram_browser.html",
        await page_context_async(
            request,
            db,
            user,
            link_token=link_token,
            auth_url=str(request.url),
            success=False,
            error=None,
        ),
    )
