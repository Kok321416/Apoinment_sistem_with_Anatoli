import hashlib
import hmac
import json
import uuid
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.auth.session import AuthUser, get_current_user, login_user, logout_user
from app.config import get_settings
from app.database import get_db
from app.deps import get_consultant
from app.models import Booking, Calendar, Category, Consultant, Integration, User
from app.services.bookings import parse_fio
from app.services.email_verification import ensure_email_address, send_user_verification_email
from app.services.telegram import format_client_booked_message, send_telegram_to_client

router = APIRouter(prefix="/api", tags=["api"])
settings = get_settings()


def _check_bot_token(request: Request) -> bool:
    token = settings.telegram_bot_token
    if not token:
        return False
    return request.headers.get("X-Bot-Token", "").strip() == token


@router.post("/auth/register")
async def api_register(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
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
    category = db.query(Category).filter(Category.name_category == "Общая").first()
    if not category:
        category = Category(name_category="Общая")
        db.add(category)
        db.flush()
    consultant = Consultant(
        user_id=user.id,
        first_name="",
        last_name="",
        middle_name="",
        email=email,
        phone="",
        telegram_nickname="",
        category_of_specialist_id=category.id,
    )
    db.add(consultant)
    ensure_email_address(db, user, email, verified=False)
    if not send_user_verification_email(db, user):
        return JSONResponse({"error": "Не удалось отправить письмо подтверждения"}, status_code=500)
    return JSONResponse({
        "message": "Письмо с подтверждением отправлено",
        "user_id": user.id,
        "consultant_id": consultant.id,
        "email": email,
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
        return JSONResponse({"error": "Подтвердите email. Проверьте почту."}, status_code=403)
    login_user(request, user)
    return {"message": "OK", "email": user.email}


@router.post("/auth/logout")
async def api_logout(request: Request):
    logout_user(request)
    return {"message": "OK"}


@router.post("/booking/confirm-telegram")
async def confirm_booking_telegram(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    link_token = (data.get("link_token") or "").strip()
    telegram_id = data.get("telegram_id")
    if not link_token or telegram_id is None:
        return JSONResponse({"success": False, "error": "link_token and telegram_id required"}, status_code=400)
    booking = db.query(Booking).filter(Booking.link_token == link_token).first()
    if not booking:
        return JSONResponse({"success": False, "error": "Invalid or expired link"}, status_code=404)
    booking.telegram_id = int(telegram_id)
    booking.link_token = None
    db.commit()
    db.refresh(booking)
    try:
        send_telegram_to_client(booking.telegram_id, format_client_booked_message(booking))
    except Exception:
        pass
    return {"success": True, "message": "Telegram привязан к записи"}


@router.post("/specialist/connect-telegram")
async def confirm_specialist_telegram(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
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
    integration.telegram_chat_id = str(int(telegram_id))
    integration.telegram_connected = True
    integration.telegram_enabled = True
    integration.telegram_link_token = None
    integration.telegram_link_token_created_at = None
    db.commit()
    return {"success": True, "message": "Telegram подключен"}


@router.post("/telegram/client-bookings")
async def api_telegram_client_bookings(request: Request, db: Session = Depends(get_db)):
    if not _check_bot_token(request):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = await request.json()
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
    if not _check_bot_token(request):
        return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    data = await request.json()
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
    booking.telegram_id = int(telegram_id)
    booking.link_token = None
    username = data.get("username") or ""
    if username and not username.startswith("@"):
        username = "@" + username
    booking.client_telegram = username
    db.commit()
    try:
        send_telegram_to_client(booking.telegram_id, format_client_booked_message(booking))
    except Exception:
        pass
    return {"success": True, "message": "Telegram привязан, сообщение отправлено"}
