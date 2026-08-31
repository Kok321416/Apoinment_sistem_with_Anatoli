import json
import logging
import secrets
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.login_flow import finish_login_async
from app.auth.session import get_current_user_async, login_user_async
from app.config import get_settings
from app.database import get_async_db
from app.deps import normalize_phone
from app.models import EmailAddress, SocialAccount, User
from app.security.csrf import validate_csrf_token
from app.services.email_verification import (
    resend_verification_email_async,
    verify_email_code_async,
    verify_email_token_async,
)
from app.services.login_methods import can_disconnect_social_async
from app.services.telegram_auth import (
    consume_completed_login_async,
    create_login_request_async,
    get_completed_login_async,
)
from app.services.yandex_auth import (
    build_authorize_url,
    complete_yandex_oauth_async,
    exchange_code_for_token,
    fetch_yandex_profile,
    yandex_oauth_configured,
)
from app.services.vk_auth import (
    build_authorize_url as build_vk_authorize_url,
    complete_vk_oauth_async,
    exchange_code_for_token as exchange_vk_code_for_token,
    fetch_vk_profile,
    generate_pkce_pair,
    vk_group_write_url,
    vk_messaging_configured,
    vk_oauth_configured,
)
from app.templating import page_context_async, templates
from app.utils.safe_redirect import safe_next_url, signup_error_redirect

router = APIRouter(prefix="/accounts", tags=["oauth"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _form_csrf_ok(request: Request, form) -> bool:
    token = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
    return validate_csrf_token(request, token)


async def _oauth_return_async(
    request: Request,
    db: AsyncSession,
    user,
    next_url: str,
    *,
    client_channel: str = "web",
    connect: bool = False,
    connect_success_message: str | None = None,
):
    """Return to browser, Capacitor, or Telegram Mini App (HTTPS bridge → reopen)."""
    from app.services.client_channel import normalize_client_channel
    from app.services.native_auth_handoff import create_native_handoff_async

    channel = normalize_client_channel(client_channel)
    if channel == "native":
        handoff = await create_native_handoff_async(db, user_id=user.id, next_url=next_url)
        if connect and connect_success_message:
            request.session["integrations_success"] = connect_success_message
        bridge = (
            f"{settings.site_url.rstrip('/')}/accounts/open-native/"
            f"?kind=handoff&token={quote(handoff.token)}"
        )
        return RedirectResponse(bridge, status_code=302)

    # Mini App WebView cannot open t.me / startapp (ERR_TIMED_OUT). Stay on this origin.
    if channel == "tg":
        if connect:
            await login_user_async(request, user, db)
            if connect_success_message:
                request.session["integrations_success"] = connect_success_message
            return RedirectResponse(next_url or "/tg/", status_code=302)
        return await finish_login_async(request, user, db, next_url or "/tg/")

    if connect:
        await login_user_async(request, user, db)
        if connect_success_message:
            request.session["integrations_success"] = connect_success_message
        return RedirectResponse(next_url, status_code=302)

    return await finish_login_async(request, user, db, next_url)


@router.get("/open-native/")
async def open_native_bridge(request: Request):
    """HTTPS page opened from Telegram/browser; jumps into Capacitor via custom scheme."""
    kind = (request.query_params.get("kind") or "").strip().lower()
    token = (request.query_params.get("token") or "").strip()
    if not token or kind not in ("complete", "handoff"):
        return RedirectResponse("/login/", status_code=302)
    if kind == "complete":
        deep = f"allyourclients://auth/complete/{token}"
        https_fallback = f"/accounts/telegram/complete/{quote(token)}/?stay=1"
    else:
        deep = f"allyourclients://auth/handoff/{token}"
        https_fallback = f"/accounts/native-handoff/{quote(token)}/"
    html = f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Открытие приложения</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0B0D12;color:#e8eaed;
font-family:system-ui,sans-serif;padding:1.5rem;text-align:center}}
a.btn{{display:inline-block;margin:.5rem;padding:.85rem 1.2rem;border-radius:12px;text-decoration:none;
background:linear-gradient(135deg,#7D5CFF,#49D1FF);color:#fff;font-weight:600}}
a.sec{{color:#9aa3b2}}
</style>
</head><body>
<p>Открываем приложение…</p>
<p><a class="btn" id="open" href="{deep}">Открыть приложение</a></p>
<p><a class="sec" href="{https_fallback}">Продолжить в браузере</a></p>
<script>
setTimeout(function(){{ window.location.href = {json.dumps(deep)}; }}, 200);
</script>
</body></html>"""
    from fastapi.responses import HTMLResponse

    return HTMLResponse(html)


@router.get("/open-tg-app/")
async def open_tg_app_bridge(request: Request):
    """HTTPS page that used to bounce to t.me; Mini App WebView must stay on this origin."""

    kind = (request.query_params.get("kind") or "").strip().lower()
    token = (request.query_params.get("token") or "").strip()
    if not token or kind not in ("complete", "handoff"):
        return RedirectResponse("/tg/", status_code=302)

    if kind == "complete":
        in_app = f"/accounts/telegram/complete/{quote(token)}/?stay=1"
    else:
        in_app = f"/accounts/native-handoff/{quote(token)}/"

    # Never auto-navigate to t.me — inside Mini App that is ERR_TIMED_OUT.
    return RedirectResponse(in_app, status_code=302)


@router.get("/native-handoff/{token}/")
async def native_auth_handoff(token: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Consume one-time token inside Capacitor WebView and finish login there."""
    from app.services.native_auth_handoff import consume_native_handoff_async

    user, next_url = await consume_native_handoff_async(db, token)
    if not user:
        return RedirectResponse("/login/?error=handoff_expired", status_code=302)
    return await finish_login_async(request, user, db, next_url)


@router.get("/telegram/login/")
async def telegram_login_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    process = request.query_params.get("process", "login")
    next_url = safe_next_url(request.query_params.get("next"))
    from app.services.client_channel import normalize_client_channel

    client_channel = normalize_client_channel(
        request.query_params.get("client") or request.session.get("oauth_client_channel")
    )
    from app.services.client_channel import remember_auth_intent

    remember_auth_intent(request.session, next_url=next_url, client_channel=client_channel)

    if process == "connect":
        if not user:
            return RedirectResponse(f"/login/?next={next_url}", status_code=302)
        req = await create_login_request_async(
            db,
            next_url=next_url,
            process="connect",
            connect_user_id=user.id,
            client_channel=client_channel,
        )
    else:
        if user:
            return RedirectResponse(next_url, status_code=302)
        register_fio = request.session.pop("register_fio", None)
        register_phone = request.session.pop("register_phone", None)
        if process in ("signup", "signup_client") and register_fio and register_phone:
            req = await create_login_request_async(
                db,
                next_url=next_url,
                process=process,
                register_fio=register_fio,
                register_phone=register_phone,
                client_channel=client_channel,
            )
        elif process in ("signup", "signup_client"):
            return RedirectResponse(signup_error_redirect(next_url, "telegram_signup"), status_code=302)
        else:
            req = await create_login_request_async(
                db, next_url=next_url, process="login", client_channel=client_channel
            )

    bot_username = settings.telegram_bot_username.lstrip("@")
    if not bot_username:
        return templates.TemplateResponse(
            "telegram_login.html",
            await page_context_async(
                request,
                db,
                user,
                error="TELEGRAM_BOT_USERNAME не настроен на сервере.",
                login_token=None,
                bot_url=None,
                next_url=next_url,
            ),
        )

    bot_url = f"https://t.me/{bot_username}?start=login_{req.token}"
    tg_app_url = f"tg://resolve?domain={bot_username}&start=login_{req.token}"
    return templates.TemplateResponse(
        "telegram_login.html",
        await page_context_async(
            request,
            db,
            user,
            login_token=req.token,
            bot_url=bot_url,
            tg_app_url=tg_app_url,
            next_url=next_url,
            error=None,
        ),
    )


@router.get("/telegram/login/status/{token}/")
async def telegram_login_status(token: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.models import TelegramLoginRequest

    req = (
        await db.execute(select(TelegramLoginRequest).where(TelegramLoginRequest.token == token))
    ).scalar_one_or_none()
    if not req:
        return JSONResponse({"completed": False, "error": "not_found"})
    if req.completed and req.complete_token:
        # Always finish on this origin. t.me / startapp inside Mini App WebView times out.
        redirect = f"/accounts/telegram/complete/{req.complete_token}/?stay=1"
        return JSONResponse({
            "completed": True,
            "redirect": redirect,
        })
    if req.expires_at < datetime.utcnow():
        return JSONResponse({"completed": False, "error": "expired"})
    return JSONResponse({"completed": False})


@router.get("/telegram/complete/{complete_token}/")
async def telegram_complete_login(
    complete_token: str, request: Request, db: AsyncSession = Depends(get_async_db)
):

    req = await get_completed_login_async(db, complete_token)
    if not req or not req.user_id:
        return RedirectResponse("/login/?error=telegram_expired", status_code=302)
    user = await db.get(User, req.user_id)
    if not user:
        return RedirectResponse("/login/", status_code=302)

    await consume_completed_login_async(db, req)
    next_url = safe_next_url(req.next_url)
    request.session["show_telegram_welcome"] = True
    return await finish_login_async(request, user, db, next_url)


@router.get("/yandex/login/")
async def yandex_login(request: Request, db: AsyncSession = Depends(get_async_db)):
    if not yandex_oauth_configured():
        return RedirectResponse("/login/?error=yandex_config", status_code=302)

    user = await get_current_user_async(request, db)
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
    from app.services.client_channel import remember_auth_intent

    remember_auth_intent(
        request.session,
        next_url=next_url,
        client_channel=request.query_params.get("client"),
    )
    return RedirectResponse(build_authorize_url(state), status_code=302)


@router.get("/yandex/callback/")
async def yandex_callback(request: Request, db: AsyncSession = Depends(get_async_db)):
    try:
        if request.query_params.get("error"):
            return RedirectResponse("/login/?error=yandex_denied", status_code=302)

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        expected_state = request.session.pop("yandex_oauth_state", None)
        process = request.session.pop("yandex_oauth_process", "login")
        next_url = safe_next_url(request.session.pop("yandex_oauth_next", "/"))
        connect_user_id = request.session.pop("yandex_connect_user_id", None)
        client_channel = request.session.pop("oauth_client_channel", "web")

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

        user, err = await complete_yandex_oauth_async(
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

        if process == "connect":
            return await _oauth_return_async(
                request,
                db,
                user,
                next_url,
                client_channel=client_channel,
                connect=True,
                connect_success_message="Яндекс привязан.",
            )

        return await _oauth_return_async(request, db, user, next_url, client_channel=client_channel)
    except Exception:
        logger.exception("Unhandled Yandex OAuth callback error")
        await db.rollback()
        next_fallback = safe_next_url(request.session.pop("yandex_oauth_next", "/"), default="/")
        return RedirectResponse(signup_error_redirect(next_fallback, "yandex_failed"), status_code=302)


@router.get("/vk/login/")
async def vk_login(request: Request, db: AsyncSession = Depends(get_async_db)):
    if not vk_oauth_configured():
        return RedirectResponse("/login/?error=vk_config", status_code=302)

    user = await get_current_user_async(request, db)
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
    from app.services.client_channel import remember_auth_intent

    remember_auth_intent(
        request.session,
        next_url=next_url,
        client_channel=request.query_params.get("client"),
    )
    return RedirectResponse(build_vk_authorize_url(state=state, code_challenge=code_challenge), status_code=302)


@router.get("/vk/callback/")
async def vk_callback(request: Request, db: AsyncSession = Depends(get_async_db)):
    try:
        if request.query_params.get("error"):
            return RedirectResponse("/login/?error=vk_denied", status_code=302)

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
        client_channel = request.session.pop("oauth_client_channel", "web")

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

            booking = (
                await db.execute(select(Booking).where(Booking.link_token == link_token))
            ).scalar_one_or_none()
            if not booking:
                return RedirectResponse("/?error=vk_booking", status_code=302)
            vk_id = str(profile.get("user_id") or profile.get("id") or "").strip()
            try:
                booking.vk_user_id = int(vk_id)
            except (TypeError, ValueError):
                return RedirectResponse("/login/?error=vk_profile", status_code=302)
            await db.commit()
            await db.refresh(booking)
            notify_client_booked_vk(booking)
            write_url = vk_group_write_url() if vk_messaging_configured() else None
            redirect = next_url if next_url and next_url != "/" else "/"
            if write_url:
                request.session["vk_allow_messages_hint"] = write_url
            return RedirectResponse(f"{redirect}?vk=confirmed", status_code=302)

        register_fio = register_phone = None
        if process in ("signup", "signup_client"):
            register_fio = (request.session.pop("register_fio", None) or "").strip() or None
            register_phone = normalize_phone(request.session.pop("register_phone", None)) or None

        user, err, _vk_id = await complete_vk_oauth_async(
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

        if process == "connect":
            return await _oauth_return_async(
                request,
                db,
                user,
                next_url,
                client_channel=client_channel,
                connect=True,
                connect_success_message="VK привязан.",
            )

        return await _oauth_return_async(request, db, user, next_url, client_channel=client_channel)
    except Exception:
        logger.exception("Unhandled VK OAuth callback error")
        await db.rollback()
        next_fallback = safe_next_url(request.session.pop("vk_oauth_next", "/"), default="/")
        return RedirectResponse(signup_error_redirect(next_fallback, "vk_failed"), status_code=302)


@router.get("/confirm-email/{token}/")
async def confirm_email(request: Request, token: str, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    db_user, err = await verify_email_token_async(db, token)
    if db_user:
        return RedirectResponse("/login/?verified=1&email=" + (db_user.email or ""), status_code=302)
    return templates.TemplateResponse(
        "email_confirm_result.html",
        await page_context_async(request, db, user, error=err, success=False),
    )


@router.get("/verify-email/")
@router.post("/verify-email/")
async def verify_email_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
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
            ok, msg = await resend_verification_email_async(db, email)
            if ok:
                success = msg
            else:
                error = msg
        else:
            email = (form.get("email") or "").strip()
            code = (form.get("code") or "").strip()
            db_user, err = await verify_email_code_async(db, email, code)
            if db_user:
                from urllib.parse import urlencode

                params = {"verified": "1", "email": db_user.email or email}
                if next_after:
                    params["next"] = next_after
                return RedirectResponse("/login/?" + urlencode(params), status_code=302)
            error = err
    return templates.TemplateResponse(
        "email_verification_sent.html",
        await page_context_async(
            request,
            db,
            user,
            email=email,
            error=error,
            success=success,
            email_verify_hours=settings.email_verify_hours,
            next_url=next_after,
        ),
    )


@router.get("/password/set/")
@router.post("/password/set/")
async def set_password_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.passwords import hash_password

    user = await get_current_user_async(request, db)
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
            db_user = await db.get(User, user.id)
            db_user.password = hash_password(p1)
            await db.commit()
            if "session" in request.scope:
                request.session["has_usable_password"] = True
            from app.auth.session import clear_request_user_cache

            clear_request_user_cache(request)
            next_url = safe_next_url(request.query_params.get("next"))
            return RedirectResponse(next_url, status_code=302)
    return templates.TemplateResponse(
        "password_set.html",
        await page_context_async(request, db, user, error=error),
    )


@router.get("/password/reset/")
@router.post("/password/reset/")
async def password_reset_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.auth.passwords import hash_password
    from app.security.csrf import validate_csrf_token
    from app.services.password_reset import consume_reset_token_async, get_valid_reset_token_async

    token = (request.query_params.get("token") or "").strip()
    error = None
    if request.method == "POST":
        form = await request.form()
        csrf = form.get("csrf_token") or form.get("csrfmiddlewaretoken")
        if not validate_csrf_token(request, csrf):
            error = "Ошибка безопасности. Обновите страницу и попробуйте снова."
            return templates.TemplateResponse(
                "password_reset.html",
                await page_context_async(request, db, None, error=error, token=token),
            )
        token = (form.get("token") or token or "").strip()
        p1 = form.get("password1", "")
        p2 = form.get("password2", "")
        row = await get_valid_reset_token_async(db, token)
        if not row:
            error = "Ссылка недействительна или истекла."
        elif p1 != p2:
            error = "Пароли не совпадают"
        elif len(p1) < 8:
            error = "Пароль должен быть не менее 8 символов"
        else:
            db_user = await db.get(User, row.user_id)
            if not db_user:
                error = "Пользователь не найден."
            else:
                db_user.password = hash_password(p1)
                await consume_reset_token_async(db, row)
                await db.commit()
                return RedirectResponse("/login/?success=password_reset", status_code=302)
    elif not token:
        error = "Укажите ссылку из письма."
    elif not await get_valid_reset_token_async(db, token):
        error = "Ссылка недействительна или истекла."
    return templates.TemplateResponse(
        "password_reset.html",
        await page_context_async(request, db, None, error=error, token=token),
    )


@router.get("/social/connections/")
@router.post("/social/connections/")
async def social_connections(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    success = error = None
    if request.method == "POST":
        form = await request.form()
        action = form.get("action")
        if action == "disconnect_telegram":
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
                success = "Телеграм отвязан."
        elif action == "disconnect_yandex":
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
                success = "Яндекс отвязан."
        elif action == "disconnect_vk":
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
                success = "VK отвязан."
        elif action == "disconnect_email":
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
                success = "Почта отвязана."
    accounts = list(
        (await db.execute(select(SocialAccount).where(SocialAccount.user_id == user.id)))
        .scalars()
        .all()
    )
    primary = (
        await db.execute(
            select(EmailAddress).where(
                EmailAddress.user_id == user.id,
                EmailAddress.primary.is_(True),
            )
        )
    ).scalar_one_or_none()
    return templates.TemplateResponse(
        "social_connections.html",
        await page_context_async(
            request,
            db,
            user,
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
        ),
    )
