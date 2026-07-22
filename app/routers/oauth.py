import json
import logging
import secrets
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import get_current_user, login_user
from app.config import get_settings
from app.database import get_db
from app.deps import normalize_phone
from app.models import EmailAddress, SocialAccount, User
from app.security.csrf import validate_csrf_token
from app.services.email_verification import resend_verification_email, verify_email_code
from app.services.login_methods import can_disconnect_social
from app.services.telegram_auth import consume_completed_login, create_login_request, get_completed_login
from app.services.yandex_auth import (
    build_authorize_url,
    complete_yandex_oauth,
    exchange_code_for_token,
    fetch_yandex_profile,
    yandex_oauth_configured,
)
from app.services.vk_auth import (
    build_authorize_url as build_vk_authorize_url,
    complete_vk_oauth,
    exchange_code_for_token as exchange_vk_code_for_token,
    fetch_vk_profile,
    generate_pkce_pair,
    vk_group_write_url,
    vk_messaging_configured,
    vk_oauth_configured,
)
from app.templating import page_context, templates
from app.utils.safe_redirect import safe_next_url, signup_error_redirect

router = APIRouter(prefix="/accounts", tags=["oauth"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _form_csrf_ok(request: Request, form) -> bool:
    token = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
    return validate_csrf_token(request, token)


@router.get("/telegram/login/")
async def telegram_login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    process = request.query_params.get("process", "login")
    next_url = safe_next_url(request.query_params.get("next"))

    if process == "connect":
        if not user:
            return RedirectResponse(f"/login/?next={next_url}", status_code=302)
        req = create_login_request(
            db,
            next_url=next_url,
            process="connect",
            connect_user_id=user.id,
        )
    else:
        if user:
            return RedirectResponse(next_url, status_code=302)
        register_fio = request.session.pop("register_fio", None)
        register_phone = request.session.pop("register_phone", None)
        if process in ("signup", "signup_client") and register_fio and register_phone:
            req = create_login_request(
                db,
                next_url=next_url,
                process=process,
                register_fio=register_fio,
                register_phone=register_phone,
            )
        elif process in ("signup", "signup_client"):
            return RedirectResponse(signup_error_redirect(next_url, "telegram_signup"), status_code=302)
        else:
            req = create_login_request(db, next_url=next_url, process="login")

    bot_username = settings.telegram_bot_username.lstrip("@")
    if not bot_username:
        return templates.TemplateResponse("telegram_login.html", page_context(
            request, db, user,
            error="TELEGRAM_BOT_USERNAME не настроен на сервере.",
            login_token=None,
            bot_url=None,
            next_url=next_url,
        ))

    bot_url = f"https://t.me/{bot_username}?start=login_{req.token}"
    tg_app_url = f"tg://resolve?domain={bot_username}&start=login_{req.token}"
    return templates.TemplateResponse("telegram_login.html", page_context(
        request, db, user,
        login_token=req.token,
        bot_url=bot_url,
        tg_app_url=tg_app_url,
        next_url=next_url,
        error=None,
    ))


@router.get("/telegram/login/status/{token}/")
async def telegram_login_status(token: str, db: Session = Depends(get_db)):
    from app.models import TelegramLoginRequest

    req = db.query(TelegramLoginRequest).filter(TelegramLoginRequest.token == token).first()
    if not req:
        return JSONResponse({"completed": False, "error": "not_found"})
    if req.completed and req.complete_token:
        return JSONResponse({
            "completed": True,
            "redirect": f"/accounts/telegram/complete/{req.complete_token}/",
        })
    if req.expires_at < datetime.utcnow():
        return JSONResponse({"completed": False, "error": "expired"})
    return JSONResponse({"completed": False})


@router.get("/telegram/complete/{complete_token}/")
async def telegram_complete_login(complete_token: str, request: Request, db: Session = Depends(get_db)):
    req = get_completed_login(db, complete_token)
    if not req or not req.user_id:
        return RedirectResponse("/login/?error=telegram_expired", status_code=302)
    user = db.get(User, req.user_id)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    login_user(request, user, db)
    request.session["show_telegram_welcome"] = True
    consume_completed_login(db, req)
    return RedirectResponse(safe_next_url(req.next_url), status_code=302)


@router.get("/yandex/login/")
async def yandex_login(request: Request, db: Session = Depends(get_db)):
    if not yandex_oauth_configured():
        return RedirectResponse("/login/?error=yandex_config", status_code=302)

    user = get_current_user(request, db)
    process = request.query_params.get("process", "login")
    next_url = safe_next_url(request.query_params.get("next"))

    if process == "connect":
        if not user:
            return RedirectResponse(f"/login/?next={quote(next_url, safe='')}", status_code=302)
        request.session["yandex_connect_user_id"] = user.id
    else:
        if user:
            return RedirectResponse(next_url, status_code=302)
        if process in ("signup", "signup_client"):
            register_fio = (request.session.get("register_fio") or "").strip()
            register_phone = normalize_phone(request.session.get("register_phone"))
            if not register_fio or not register_phone:
                return RedirectResponse(signup_error_redirect(next_url, "yandex_signup"), status_code=302)

    state = secrets.token_urlsafe(32)
    request.session["yandex_oauth_state"] = state
    request.session["yandex_oauth_process"] = process
    request.session["yandex_oauth_next"] = next_url
    return RedirectResponse(build_authorize_url(state), status_code=302)


@router.get("/yandex/callback/")
async def yandex_callback(request: Request, db: Session = Depends(get_db)):
    try:
        if request.query_params.get("error"):
            return RedirectResponse("/login/?error=yandex_denied", status_code=302)

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        expected_state = request.session.pop("yandex_oauth_state", None)
        process = request.session.pop("yandex_oauth_process", "login")
        next_url = safe_next_url(request.session.pop("yandex_oauth_next", "/"))
        connect_user_id = request.session.pop("yandex_connect_user_id", None)

        if not code or not state or not expected_state or not secrets.compare_digest(state, expected_state):
            return RedirectResponse("/login/?error=yandex_state", status_code=302)

        token_data = exchange_code_for_token(code)
        access_token = (token_data or {}).get("access_token")
        if not access_token:
            return RedirectResponse("/login/?error=yandex_token", status_code=302)

        profile = fetch_yandex_profile(access_token)
        if not profile:
            return RedirectResponse("/login/?error=yandex_profile", status_code=302)

        register_fio = register_phone = None
        if process in ("signup", "signup_client"):
            register_fio = (request.session.pop("register_fio", None) or "").strip() or None
            register_phone = normalize_phone(request.session.pop("register_phone", None)) or None

        user, err = complete_yandex_oauth(
            db,
            process=process,
            profile=profile,
            register_fio=register_fio,
            register_phone=register_phone,
            connect_user_id=connect_user_id,
        )
        if err or not user:
            if process in ("signup", "signup_client"):
                return RedirectResponse(signup_error_redirect(next_url, "yandex_failed"), status_code=302)
            return RedirectResponse("/login/?error=yandex_failed", status_code=302)

        login_user(request, user, db)
        if process == "connect":
            request.session["integrations_success"] = "Яндекс привязан."
        return RedirectResponse(next_url, status_code=302)
    except Exception:
        logger.exception("Unhandled Yandex OAuth callback error")
        db.rollback()
        next_fallback = safe_next_url(request.session.pop("yandex_oauth_next", "/"), default="/")
        return RedirectResponse(signup_error_redirect(next_fallback, "yandex_failed"), status_code=302)


@router.get("/vk/login/")
async def vk_login(request: Request, db: Session = Depends(get_db)):
    if not vk_oauth_configured():
        return RedirectResponse("/login/?error=vk_config", status_code=302)

    user = get_current_user(request, db)
    process = request.query_params.get("process", "login")
    next_url = safe_next_url(request.query_params.get("next"))

    if process == "connect":
        if not user:
            return RedirectResponse(f"/login/?next={quote(next_url, safe='')}", status_code=302)
        request.session["vk_connect_user_id"] = user.id
    elif process == "link_booking":
        link_token = (request.query_params.get("link_token") or "").strip()
        if not link_token:
            return RedirectResponse("/", status_code=302)
        request.session["vk_link_booking_token"] = link_token
    else:
        if user:
            return RedirectResponse(next_url, status_code=302)
        if process in ("signup", "signup_client"):
            register_fio = (request.session.get("register_fio") or "").strip()
            register_phone = normalize_phone(request.session.get("register_phone"))
            if not register_fio or not register_phone:
                return RedirectResponse(signup_error_redirect(next_url, "vk_signup"), status_code=302)

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce_pair()
    request.session["vk_oauth_state"] = state
    request.session["vk_oauth_process"] = process
    request.session["vk_oauth_next"] = next_url
    request.session["vk_code_verifier"] = code_verifier
    return RedirectResponse(build_vk_authorize_url(state=state, code_challenge=code_challenge), status_code=302)


@router.get("/vk/callback/")
async def vk_callback(request: Request, db: Session = Depends(get_db)):
    try:
        if request.query_params.get("error"):
            return RedirectResponse("/login/?error=vk_denied", status_code=302)

        # VK ID may return flat params or JSON payload=
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        device_id = request.query_params.get("device_id") or ""
        payload_raw = request.query_params.get("payload")
        if payload_raw and (not code or not state):
            try:
                payload = json.loads(payload_raw)
                code = code or payload.get("code")
                state = state or payload.get("state")
                device_id = device_id or (payload.get("device_id") or "")
            except Exception:
                logger.exception("Failed to parse VK payload")

        expected_state = request.session.pop("vk_oauth_state", None)
        process = request.session.pop("vk_oauth_process", "login")
        next_url = safe_next_url(request.session.pop("vk_oauth_next", "/"))
        connect_user_id = request.session.pop("vk_connect_user_id", None)
        code_verifier = request.session.pop("vk_code_verifier", None)
        link_token = request.session.pop("vk_link_booking_token", None)

        if (
            not code
            or not state
            or not expected_state
            or not code_verifier
            or not secrets.compare_digest(state, expected_state)
        ):
            return RedirectResponse("/login/?error=vk_state", status_code=302)

        if not device_id:
            return RedirectResponse("/login/?error=vk_token", status_code=302)

        token_data = exchange_vk_code_for_token(
            code=code,
            code_verifier=code_verifier,
            device_id=device_id,
            state=state,
        )
        access_token = (token_data or {}).get("access_token")
        if not access_token:
            return RedirectResponse("/login/?error=vk_token", status_code=302)

        profile = fetch_vk_profile(access_token)
        if not profile and token_data.get("user_id"):
            profile = {"user_id": token_data["user_id"]}
        if not profile:
            return RedirectResponse("/login/?error=vk_profile", status_code=302)

        if process == "link_booking" and link_token:
            from app.models import Booking
            from app.services.vk_messages import notify_client_booked_vk

            booking = db.query(Booking).filter(Booking.link_token == link_token).first()
            if not booking:
                return RedirectResponse("/?error=vk_booking", status_code=302)
            vk_id = str(profile.get("user_id") or profile.get("id") or "").strip()
            try:
                booking.vk_user_id = int(vk_id)
            except (TypeError, ValueError):
                return RedirectResponse("/login/?error=vk_profile", status_code=302)
            db.commit()
            db.refresh(booking)
            notify_client_booked_vk(booking)
            write_url = vk_group_write_url() if vk_messaging_configured() else None
            # Prefer returning to booking success if we know calendar; else dashboard
            redirect = next_url if next_url and next_url != "/" else "/"
            if write_url:
                # After OAuth, ask user to allow community messages
                request.session["vk_allow_messages_hint"] = write_url
            return RedirectResponse(f"{redirect}?vk=confirmed", status_code=302)

        register_fio = register_phone = None
        if process in ("signup", "signup_client"):
            register_fio = (request.session.pop("register_fio", None) or "").strip() or None
            register_phone = normalize_phone(request.session.pop("register_phone", None)) or None

        user, err, _vk_id = complete_vk_oauth(
            db,
            process=process,
            profile=profile,
            register_fio=register_fio,
            register_phone=register_phone,
            connect_user_id=connect_user_id,
        )
        if err or not user:
            if process in ("signup", "signup_client"):
                return RedirectResponse(signup_error_redirect(next_url, "vk_failed"), status_code=302)
            return RedirectResponse("/login/?error=vk_failed", status_code=302)

        login_user(request, user, db)
        if process == "connect":
            request.session["integrations_success"] = "VK привязан."
            if vk_messaging_configured():
                write_url = vk_group_write_url()
                if write_url:
                    request.session["vk_allow_messages_hint"] = write_url
        return RedirectResponse(next_url, status_code=302)
    except Exception:
        logger.exception("Unhandled VK OAuth callback error")
        db.rollback()
        next_fallback = safe_next_url(request.session.pop("vk_oauth_next", "/"), default="/")
        return RedirectResponse(signup_error_redirect(next_fallback, "vk_failed"), status_code=302)


@router.get("/confirm-email/{token}/")
async def confirm_email(request: Request, token: str, db: Session = Depends(get_db)):
    from app.services.email_verification import verify_email_token

    user = get_current_user(request, db)
    db_user, err = verify_email_token(db, token)
    if db_user:
        return RedirectResponse("/login/?verified=1&email=" + (db_user.email or ""), status_code=302)
    return templates.TemplateResponse("email_confirm_result.html", page_context(
        request, db, user, error=err, success=False,
    ))


@router.get("/verify-email/")
@router.post("/verify-email/")
async def verify_email_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    next_after = safe_next_url(request.query_params.get("next"), default="")
    if user and user.is_active:
        return RedirectResponse(next_after or "/dashboard/", status_code=302)
    email = (request.query_params.get("email") or "").strip()
    error = success = None
    if request.method == "POST":
        form = await request.form()
        next_after = safe_next_url(form.get("next") or next_after, default="")
        if not _form_csrf_ok(request, form):
            error = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
            email = (form.get("email") or email or "").strip()
        elif form.get("action") == "resend":
            email = (form.get("email") or "").strip()
            ok, msg = resend_verification_email(db, email)
            if ok:
                success = msg
            else:
                error = msg
        else:
            email = (form.get("email") or "").strip()
            code = (form.get("code") or "").strip()
            db_user, err = verify_email_code(db, email, code)
            if db_user:
                from urllib.parse import urlencode

                params = {"verified": "1", "email": db_user.email or email}
                if next_after:
                    params["next"] = next_after
                return RedirectResponse("/login/?" + urlencode(params), status_code=302)
            error = err
    return templates.TemplateResponse("email_verification_sent.html", page_context(
        request, db, user,
        email=email,
        error=error,
        success=success,
        email_verify_hours=settings.email_verify_hours,
        next_url=next_after,
    ))


@router.get("/password/set/")
@router.post("/password/set/")
async def set_password_page(request: Request, db: Session = Depends(get_db)):
    from app.auth.passwords import hash_password

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    if user.has_usable_password:
        return RedirectResponse("/dashboard/", status_code=302)
    error = None
    if request.method == "POST":
        form = await request.form()
        p1 = form.get("password1", "")
        p2 = form.get("password2", "")
        if p1 != p2:
            error = "Пароли не совпадают"
        elif len(p1) < 8:
            error = "Пароль должен быть не менее 8 символов"
        else:
            db_user = db.get(User, user.id)
            db_user.password = hash_password(p1)
            db.commit()
            if "session" in request.scope:
                request.session["has_usable_password"] = True
            from app.auth.session import clear_request_user_cache

            clear_request_user_cache(request)
            next_url = safe_next_url(request.query_params.get("next"))
            return RedirectResponse(next_url, status_code=302)
    return templates.TemplateResponse("password_set.html", page_context(request, db, user, error=error))


@router.get("/password/reset/")
@router.post("/password/reset/")
async def password_reset_page(request: Request, db: Session = Depends(get_db)):
    from app.auth.passwords import hash_password
    from app.services.password_reset import consume_reset_token, get_valid_reset_token

    token = (request.query_params.get("token") or "").strip()
    error = None
    if request.method == "POST":
        form = await request.form()
        token = (form.get("token") or token or "").strip()
        p1 = form.get("password1", "")
        p2 = form.get("password2", "")
        row = get_valid_reset_token(db, token)
        if not row:
            error = "Ссылка недействительна или истекла."
        elif p1 != p2:
            error = "Пароли не совпадают"
        elif len(p1) < 8:
            error = "Пароль должен быть не менее 8 символов"
        else:
            db_user = db.get(User, row.user_id)
            if not db_user:
                error = "Пользователь не найден."
            else:
                db_user.password = hash_password(p1)
                consume_reset_token(db, row)
                db.commit()
                return RedirectResponse("/login/?success=password_reset", status_code=302)
    elif not token:
        error = "Укажите ссылку из письма."
    elif not get_valid_reset_token(db, token):
        error = "Ссылка недействительна или истекла."
    return templates.TemplateResponse(
        "password_reset.html",
        page_context(request, db, None, error=error, token=token),
    )


@router.get("/social/connections/")
@router.post("/social/connections/")
async def social_connections(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "disconnect_telegram":
            ok, msg = can_disconnect_social(db, user, "telegram")
            if not ok:
                error = msg
            else:
                for acc in db.query(SocialAccount).filter(
                    SocialAccount.user_id == user.id, SocialAccount.provider == "telegram"
                ).all():
                    db.delete(acc)
                db.commit()
                success = "Телеграм отвязан."
        elif action == "disconnect_yandex":
            ok, msg = can_disconnect_social(db, user, "yandex")
            if not ok:
                error = msg
            else:
                for acc in db.query(SocialAccount).filter(
                    SocialAccount.user_id == user.id, SocialAccount.provider == "yandex"
                ).all():
                    db.delete(acc)
                db.commit()
                success = "Яндекс отвязан."
        elif action == "disconnect_vk":
            ok, msg = can_disconnect_social(db, user, "vk")
            if not ok:
                error = msg
            else:
                for acc in db.query(SocialAccount).filter(
                    SocialAccount.user_id == user.id, SocialAccount.provider == "vk"
                ).all():
                    db.delete(acc)
                db.commit()
                success = "VK отвязан."
        elif action == "disconnect_email":
            rows = db.query(EmailAddress).filter(EmailAddress.user_id == user.id).all()
            has_social = db.query(SocialAccount).filter(
                SocialAccount.user_id == user.id,
                SocialAccount.provider.in_(("telegram", "yandex", "vk")),
            ).first()
            if not rows or not any(r.verified for r in rows):
                error = "Подтверждённая почта не привязана."
            elif not user.has_usable_password and not has_social:
                error = "Нельзя отвязать почту: сначала привяжите Телеграм, Яндекс, VK или задайте пароль."
            else:
                for row in rows:
                    row.verified = False
                db.commit()
                success = "Почта отвязана."
    accounts = db.query(SocialAccount).filter(SocialAccount.user_id == user.id).all()
    primary = db.query(EmailAddress).filter(EmailAddress.user_id == user.id, EmailAddress.primary.is_(True)).first()
    return templates.TemplateResponse("social_connections.html", page_context(
        request, db, user,
        social_accounts=accounts,
        has_telegram=any(a.provider == "telegram" for a in accounts),
        has_yandex=any(a.provider == "yandex" for a in accounts),
        has_vk=any(a.provider == "vk" for a in accounts),
        yandex_oauth_enabled=yandex_oauth_configured(),
        vk_oauth_enabled=vk_oauth_configured(),
        email_address=primary.email if primary else (user.email or ""),
        email_verified=bool(primary and primary.verified),
        success=success,
        error=error,
    ))
