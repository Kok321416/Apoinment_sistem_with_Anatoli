import hashlib
import hmac
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.auth.session import get_current_user, login_user, logout_user
from app.config import get_settings
from app.database import get_db
from app.models import Booking, Calendar, Category, Consultant, Integration, User
from app.security.bot_api import verify_bot_request
from app.services.bookings import parse_fio
from app.services.email_verification import ensure_email_address, send_user_verification_email
from app.services.telegram import format_client_booked_message, send_telegram_to_client
from app.services.dual_role_backfill import resolve_client_user_id_for_telegram
from app.services.integration_telegram import claim_integration_telegram_chat

router = APIRouter(prefix="/api", tags=["api"])
settings = get_settings()
logger = logging.getLogger(__name__)

BOOKING_LINK_TTL_SECONDS = 48 * 3600


async def _require_bot(request: Request) -> bytes:
    body = await request.body()
    if not verify_bot_request(request, body):
        raise HTTPException(status_code=403, detail="Forbidden")
    return body


def _booking_link_expired(booking: Booking) -> bool:
    if not booking.created_at:
        return False
    return (datetime.utcnow() - booking.created_at).total_seconds() > BOOKING_LINK_TTL_SECONDS


@router.post("/auth/register")
async def api_register(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    role = (data.get("role") or "specialist").strip().lower()
    if settings.force_consultant_on_signup:
        role = "specialist"
    if db.query(User).filter(User.username == email).first():
        return JSONResponse({"error": "Уже зарегистрирован"}, status_code=400)
    user = User(
        username=email,
        email=email,
        password=hash_password(password),
        is_active=False,
        date_joined=datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    consultant_id = None
    if role != "client":
        from app.services.consultant_onboarding import create_consultant_for_user

        fio = (data.get("fio") or "").strip() or email
        phone = (data.get("phone") or "").strip() or "+70000000000"
        consultant = create_consultant_for_user(db, user, fio=fio, phone=phone, email=email)
        consultant_id = consultant.id
    ensure_email_address(db, user, email, verified=False)
    if not send_user_verification_email(db, user):
        db.rollback()
        return JSONResponse({"error": "Не удалось отправить письмо с кодом подтверждения"}, status_code=500)
    return JSONResponse({
        "message": "Вам на почту отправлено письмо. Введите 6-значный код на странице подтверждения.",
        "user_id": user.id,
        "consultant_id": consultant_id,
        "role": role if role == "client" else "specialist",
        "email": email,
        "verify_url": f"/accounts/verify-email/?email={email}",
    }, status_code=201)


@router.post("/auth/login")
async def api_login(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    user = db.query(User).filter(User.username == email).first()
    if not user or not verify_password(password, user.password):
        return JSONResponse({"error": "Неверный логин/пароль"}, status_code=401)
    if not user.is_active:
        return JSONResponse({"error": "Подтвердите почту. Проверьте письмо."}, status_code=403)
    login_user(request, user)
    return {"message": "OK", "email": user.email}


@router.post("/auth/logout")
async def api_logout(request: Request):
    logout_user(request)
    return {"message": "OK"}


@router.post("/telegram/confirm-login")
async def confirm_telegram_login(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    token = (data.get("token") or "").strip()
    telegram_id = data.get("telegram_id")
    if not token or telegram_id is None:
        return JSONResponse({"success": False, "error": "token and telegram_id required"}, status_code=400)
    from app.services.telegram_auth import confirm_login_via_bot

    ok, msg, req = confirm_login_via_bot(
        db,
        token,
        telegram_id,
        username=(data.get("username") or "").strip(),
        first_name=(data.get("first_name") or "").strip(),
    )
    if not ok or not req:
        return JSONResponse({"success": False, "error": msg}, status_code=400)
    site = settings.site_url.rstrip("/")
    return {
        "success": True,
        "complete_url": f"{site}/accounts/telegram/complete/{req.complete_token}/",
        "next_url": req.next_url,
    }


@router.post("/booking/confirm-telegram")
async def confirm_booking_telegram(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    link_token = (data.get("link_token") or "").strip()
    telegram_id = data.get("telegram_id")
    if not link_token or telegram_id is None:
        return JSONResponse({"success": False, "error": "link_token and telegram_id required"}, status_code=400)
    booking = db.query(Booking).filter(Booking.link_token == link_token).first()
    if not booking:
        return JSONResponse({"success": False, "error": "Invalid or expired link"}, status_code=404)
    # TTL: 48 hours from booking creation
    if _booking_link_expired(booking):
        booking.link_token = None
        db.commit()
        return JSONResponse({"success": False, "error": "Ссылка истекла"}, status_code=400)
    tid = int(telegram_id)
    # Idempotent re-confirm
    if booking.telegram_id and int(booking.telegram_id) == tid:
        if booking.client_user_id is None:
            booking.client_user_id = resolve_client_user_id_for_telegram(db, tid)
        booking.link_token = None
        db.commit()
        return {"success": True, "message": "Телеграм уже привязан к записи"}
    booking.telegram_id = tid
    if booking.client_user_id is None:
        booking.client_user_id = resolve_client_user_id_for_telegram(db, tid)
    booking.link_token = None
    db.commit()
    db.refresh(booking)
    try:
        send_telegram_to_client(booking.telegram_id, format_client_booked_message(booking))
    except Exception:
        logger.exception("confirm-telegram client notify failed")
    return {"success": True, "message": "Телеграм привязан к записи"}


@router.post("/specialist/connect-telegram")
async def confirm_specialist_telegram(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    link_token = (data.get("link_token") or "").strip()
    telegram_id = data.get("telegram_id")
    if not link_token or telegram_id is None:
        return JSONResponse({"success": False, "error": "link_token and telegram_id required"}, status_code=400)
    integration = db.query(Integration).filter(Integration.telegram_link_token == link_token).first()
    if not integration:
        return JSONResponse({"success": False, "error": "Ссылка недействительна или уже использована"}, status_code=404)
    if integration.telegram_link_token_created_at:
        age = (datetime.utcnow() - integration.telegram_link_token_created_at).total_seconds()
        if age > 1800:
            integration.telegram_link_token = None
            integration.telegram_link_token_created_at = None
            db.commit()
            return JSONResponse({"success": False, "error": "Ссылка истекла"}, status_code=400)
    ok, err = claim_integration_telegram_chat(
        db, integration, str(int(telegram_id)), source="bot_connect_spec"
    )
    if not ok:
        return JSONResponse({"success": False, "error": err}, status_code=409)
    integration.telegram_link_token = None
    integration.telegram_link_token_created_at = None
    db.commit()
    return {"success": True, "message": "Телеграм подключен"}


@router.post("/telegram/client-bookings")
async def api_telegram_client_bookings(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    telegram_id = data.get("telegram_id")
    if telegram_id is None:
        return JSONResponse({"success": False, "error": "telegram_id required"}, status_code=400)
    bookings = (
        db.query(Booking)
        .filter(Booking.telegram_id == int(telegram_id), Booking.status != "cancelled")
        .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
        .limit(20)
        .all()
    )
    now = datetime.utcnow().date()
    items = []
    for b in bookings:
        consultant_name = "—"
        if b.calendar and b.calendar.consultant:
            c = b.calendar.consultant
            consultant_name = f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email
        items.append({
            "id": b.id,
            "date": b.booking_date.isoformat(),
            "time": b.booking_time.strftime("%H:%M") if b.booking_time else "—",
            "service_name": b.service.name if b.service else "Консультация",
            "consultant_name": consultant_name,
            "calendar_id": b.calendar_id,
            "status": b.status,
            "is_upcoming": b.booking_date >= now,
        })
    return {"success": True, "bookings": items}


@router.post("/telegram/specialist-bookings")
async def api_telegram_specialist_bookings(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    raw = data.get("telegram_chat_id")
    if raw is None:
        return JSONResponse({"success": False, "error": "telegram_chat_id required"}, status_code=400)
    integration = db.query(Integration).filter(Integration.telegram_chat_id == str(raw).strip()).first()
    if not integration:
        return {"success": True, "bookings": [], "is_specialist": False}
    bookings = (
        db.query(Booking)
        .join(Calendar, Booking.calendar_id == Calendar.id)
        .filter(Calendar.consultant_id == integration.consultant_id, Booking.status != "cancelled")
        .order_by(Booking.booking_date, Booking.booking_time)
        .all()
    )
    now_dt = datetime.now()
    items = []
    for b in bookings:
        dt = datetime.combine(b.booking_date, b.booking_time)
        items.append({
            "id": b.id,
            "date": b.booking_date.isoformat(),
            "time": b.booking_time.strftime("%H:%M") if b.booking_time else "—",
            "client_name": b.client_name,
            "service_name": b.service.name if b.service else "Консультация",
            "status": b.status,
            "is_upcoming": dt >= now_dt,
        })
    items.sort(key=lambda x: (not x["is_upcoming"], x["date"], x["time"]))
    return {"success": True, "bookings": items[:30], "is_specialist": True}


@router.post("/telegram/capabilities")
async def api_telegram_capabilities(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    from app.services.telegram_capabilities import resolve_capabilities

    return resolve_capabilities(
        db,
        telegram_id=data.get("telegram_id"),
        telegram_chat_id=data.get("telegram_chat_id"),
    )


@router.post("/telegram/ui-mode")
async def api_telegram_ui_mode(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_bot_request(request, body):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = json.loads(body)
    from app.services.telegram_capabilities import get_ui_mode, set_ui_mode

    chat_id = data.get("telegram_chat_id") or data.get("chat_id")
    mode = data.get("mode")
    if mode:
        ok, err = set_ui_mode(db, str(chat_id or ""), str(mode))
        if not ok:
            return JSONResponse({"success": False, "error": err}, status_code=400)
        return {"success": True, "mode": mode}
    stored = get_ui_mode(db, str(chat_id or ""))
    return {"success": True, "mode": stored}


@router.post("/telegram/webapp-auth")
async def api_telegram_webapp_auth(request: Request, db: Session = Depends(get_db)):
    """Login (or create client user) from Telegram Mini App initData."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    init_data = (data.get("init_data") or data.get("initData") or "").strip()
    mode = (data.get("mode") or "").strip().lower()
    from app.services.active_mode import VALID_MODES, set_active_mode, user_has_consultant
    from app.services.telegram_webapp_auth import find_or_create_user_from_webapp, validate_webapp_init_data

    parsed = validate_webapp_init_data(init_data)
    if not parsed:
        return JSONResponse({"success": False, "error": "Invalid initData"}, status_code=401)
    tg_user = parsed.get("user") or {}
    user = find_or_create_user_from_webapp(db, tg_user)
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=400)
    login_user(request, user)
    has_c = user_has_consultant(db, user.id)
    if mode in VALID_MODES:
        set_active_mode(request, mode, has_consultant=has_c)
    return {
        "success": True,
        "user_id": user.id,
        "has_consultant": has_c,
        "created": False,
    }



def _verify_telegram_widget_hash(payload: dict, received_hash: str) -> bool:
    bot_token = settings.telegram_bot_token
    if not bot_token or not received_hash:
        return False
    data_check_string = "\n".join(f"{k}={payload[k]}" for k in sorted(payload.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_hash)


@router.post("/booking/confirm-telegram-browser")
async def confirm_booking_telegram_browser_api(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    link_token = (data.get("link_token") or "").strip()
    telegram_id = data.get("id")
    received_hash = (data.get("hash") or "").strip()
    if not link_token or telegram_id is None or not received_hash:
        return JSONResponse({"success": False, "error": "link_token, id and hash required"}, status_code=400)
    payload = {k: str(data[k]) for k in ["id", "first_name", "username", "auth_date"] if k in data and data[k] is not None}
    if "id" not in payload:
        payload["id"] = str(telegram_id)
    if not _verify_telegram_widget_hash(payload, received_hash):
        return JSONResponse({"success": False, "error": "Invalid signature"}, status_code=400)
    booking = db.query(Booking).filter(Booking.link_token == link_token).first()
    if not booking:
        return JSONResponse({"success": False, "error": "Invalid or expired link"}, status_code=404)
    if _booking_link_expired(booking):
        booking.link_token = None
        db.commit()
        return JSONResponse({"success": False, "error": "Ссылка истекла"}, status_code=400)
    tid = int(telegram_id)
    if booking.telegram_id and int(booking.telegram_id) == tid:
        if booking.client_user_id is None:
            booking.client_user_id = resolve_client_user_id_for_telegram(db, tid)
        booking.link_token = None
        db.commit()
        return {"success": True, "message": "Телеграм уже привязан, сообщение отправлено"}
    booking.telegram_id = tid
    if booking.client_user_id is None:
        booking.client_user_id = resolve_client_user_id_for_telegram(db, tid)
    booking.link_token = None
    username = data.get("username") or ""
    if username and not username.startswith("@"):
        username = "@" + username
    booking.client_telegram = username
    db.commit()
    try:
        send_telegram_to_client(booking.telegram_id, format_client_booked_message(booking))
    except Exception:
        logger.exception("confirm-telegram-browser notify failed")
    return {"success": True, "message": "Телеграм привязан, сообщение отправлено"}
