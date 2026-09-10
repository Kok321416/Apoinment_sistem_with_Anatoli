"""Specialist-created bookings API (cabinet)."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.deps import require_specialist_mode_async
from app.models import Calendar, Service
from app.security.csrf import validate_csrf_token
from app.services.bookings import (
    create_specialist_booking_async,
    search_client_cards_async,
    serialize_client_card_match,
)
from app.services.calendar_blocks import (
    cancel_calendar_block_async,
    create_calendar_block_async,
    serialize_block,
)
from app.services.slots import get_available_slots_async

router = APIRouter(prefix="/api/specialist", tags=["specialist-booking"])


async def _require_user(request: Request, db: AsyncSession):
    from app.auth.session import get_current_user_async

    return await get_current_user_async(request, db)


@router.get("/clients/")
async def search_clients(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_async_db),
):
    """Search specialist CRM cards by name, telegram, phone or email."""
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    cards = await search_client_cards_async(db, consultant.id, q)
    return {"clients": [serialize_client_card_match(c) for c in cards]}


@router.get("/calendars/")
async def list_calendars(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    rows = list(
        (
            await db.execute(
                select(Calendar)
                .where(Calendar.consultant_id == consultant.id)
                .order_by(Calendar.name)
            )
        )
        .scalars()
        .all()
    )
    return {
        "calendars": [
            {
                "id": c.id,
                "name": c.name,
                "is_active": bool(c.is_active),
                "color": c.color,
            }
            for c in rows
        ]
    }


@router.get("/services/")
async def list_services(
    request: Request,
    calendar_id: int | None = None,
    db: AsyncSession = Depends(get_async_db),
):
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    q = select(Service).where(
        Service.consultant_id == consultant.id,
        Service.is_active.is_(True),
    )
    if calendar_id is not None:
        q = q.where((Service.calendar_id == calendar_id) | (Service.calendar_id.is_(None)))
    rows = list((await db.execute(q.order_by(Service.name))).scalars().all())
    return {
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "duration_minutes": s.duration_minutes,
                "price": s.price,
                "calendar_id": s.calendar_id,
            }
            for s in rows
        ]
    }


@router.get("/slots/")
async def specialist_slots(
    request: Request,
    calendar_id: int,
    service_id: int,
    booking_date: str,
    exclude_booking_id: int | None = None,
    db: AsyncSession = Depends(get_async_db),
):
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    try:
        day = date.fromisoformat(booking_date)
    except ValueError:
        return JSONResponse({"error": "Некорректная дата"}, status_code=400)
    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    service = (
        await db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not calendar or not service:
        return JSONResponse({"error": "Календарь или услуга не найдены"}, status_code=404)
    return await get_available_slots_async(
        db, calendar, service, day, exclude_booking_id=exclude_booking_id
    )


@router.post("/bookings/")
async def create_booking(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    data = await request.json()
    csrf = data.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not validate_csrf_token(request, csrf):
        return JSONResponse({"error": "Ошибка безопасности (CSRF)"}, status_code=403)

    try:
        booking_date = date.fromisoformat((data.get("booking_date") or "").strip())
    except ValueError:
        return JSONResponse({"error": "Некорректная дата"}, status_code=400)

    try:
        calendar_id = int(data.get("calendar_id"))
        service_id = int(data.get("service_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Укажите календарь и услугу"}, status_code=400)

    client_card_id = data.get("client_card_id")
    if client_card_id is not None:
        try:
            client_card_id = int(client_card_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Некорректная карточка клиента"}, status_code=400)

    booking, err, matches = await create_specialist_booking_async(
        db,
        consultant,
        calendar_id=calendar_id,
        service_id=service_id,
        booking_date=booking_date,
        booking_time_str=(data.get("booking_time") or "").strip(),
        booking_end_time_str=(data.get("booking_end_time") or "").strip(),
        client_name=(data.get("client_name") or "").strip(),
        client_phone=(data.get("client_phone") or "").strip(),
        client_email=(data.get("client_email") or "").strip(),
        client_telegram=(data.get("client_telegram") or "").strip(),
        client_card_id=client_card_id,
        force_new_client=bool(data.get("force_new_client")),
    )
    if err == "found_matches":
        return JSONResponse(
            {
                "error": "found_matches",
                "message": "Найдены похожие клиенты. Выберите карточку или создайте новую.",
                "matches": matches or [],
            },
            status_code=409,
        )
    if err or not booking:
        return JSONResponse({"error": err or "Не удалось создать запись"}, status_code=400)

    return {
        "ok": True,
        "booking": {
            "id": booking.id,
            "client_name": booking.client_name,
            "booking_date": booking.booking_date.isoformat(),
            "booking_time": booking.booking_time.strftime("%H:%M"),
            "status": booking.status,
            "source": booking.source,
            "service": booking.service.name if booking.service else None,
            "calendar": booking.calendar.name if booking.calendar else None,
        },
    }


@router.post("/events/")
async def create_calendar_event(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Create a calendar block (мероприятие) that occupies time."""
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    data = await request.json()
    csrf = data.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not validate_csrf_token(request, csrf):
        return JSONResponse({"error": "Ошибка безопасности (CSRF)"}, status_code=403)

    try:
        block_date = date.fromisoformat((data.get("block_date") or data.get("booking_date") or "").strip())
    except ValueError:
        return JSONResponse({"error": "Некорректная дата"}, status_code=400)

    try:
        calendar_id = int(data.get("calendar_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Укажите календарь"}, status_code=400)

    block, err = await create_calendar_block_async(
        db,
        consultant,
        calendar_id=calendar_id,
        title=(data.get("title") or "").strip(),
        block_date=block_date,
        start_time_str=(data.get("start_time") or data.get("booking_time") or "").strip(),
        end_time_str=(data.get("end_time") or data.get("booking_end_time") or "").strip(),
        notes=(data.get("notes") or "").strip(),
        created_by_user_id=user.id,
    )
    if err or not block:
        return JSONResponse({"error": err or "Не удалось создать мероприятие"}, status_code=400)

    return {"ok": True, "event": serialize_block(block)}


@router.post("/events/{block_id}/cancel/")
async def cancel_calendar_event(
    block_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"error": "Требуется вход"}, status_code=401)
    consultant = await require_specialist_mode_async(request, db, user)
    data = {}
    try:
        data = await request.json()
    except Exception:
        data = {}
    csrf = (data.get("csrf_token") if isinstance(data, dict) else None) or request.headers.get(
        "X-CSRF-Token"
    )
    if not validate_csrf_token(request, csrf):
        return JSONResponse({"error": "Ошибка безопасности (CSRF)"}, status_code=403)

    block, err = await cancel_calendar_block_async(db, consultant, block_id)
    if err or not block:
        return JSONResponse({"error": err or "Не удалось отменить"}, status_code=400)
    return {"ok": True, "event": serialize_block(block)}
