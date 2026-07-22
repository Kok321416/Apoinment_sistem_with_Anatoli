"""REST endpoints for calendar schedule editor."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.session import get_current_user
from app.database import get_db
from app.deps import require_specialist_mode
from app.models import Calendar, TimeSlot, User
from app.security.csrf import validate_csrf_token
from app.services.calendar_schedule import (
    build_day_payload,
    build_schedule_payload,
    clear_day_slots,
    copy_day_slots,
    parse_time_str,
    preset_fulltime,
    preset_workweek,
    set_day_working,
    slots_by_day,
    validate_slot_times,
)
from app.services.entity_delete import delete_time_slot

router = APIRouter(tags=["calendar-schedule"])
logger = logging.getLogger(__name__)


def _json_csrf_ok(request: Request, token: str | None) -> bool:
    return validate_csrf_token(request, token)


def _csrf_from_request(request: Request, data: dict | None = None) -> str | None:
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token
    if data:
        return data.get("csrf_token")
    return None


def _require_calendar(request: Request, db: Session, calendar_id: int) -> tuple[User, Calendar]:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    consultant = require_specialist_mode(request, db, user)
    calendar = (
        db.query(Calendar)
        .filter(Calendar.id == calendar_id, Calendar.consultant_id == consultant.id)
        .first()
    )
    if not calendar:
        raise HTTPException(status_code=404, detail="Календарь не найден")
    return user, calendar


def _require_slot(db: Session, calendar: Calendar, slot_id: int) -> TimeSlot:
    slot = (
        db.query(TimeSlot)
        .filter(TimeSlot.id == slot_id, TimeSlot.calendar_id == calendar.id)
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Временное окно не найдено")
    return slot


def _schedule_response(calendar: Calendar, db: Session, *, bust: bool = False) -> dict:
    from app.services.response_cache import TTL_SEC, invalidate_calendar, schedule_key
    from app.services.ttl_cache import CACHE

    if bust:
        invalidate_calendar(calendar.id, consultant_id=calendar.consultant_id)

    def _build() -> dict:
        grouped = slots_by_day(db, calendar.id)
        return build_schedule_payload(calendar, grouped)

    return CACHE.get_or_set(schedule_key(calendar.id), _build, ttl=TTL_SEC)


def _commit_db(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("calendar schedule commit failed")
        raise HTTPException(
            status_code=400,
            detail="Не удалось сохранить расписание. Возможно, окно используется в записях.",
        ) from exc


class TimeSlotCreate(BaseModel):
    calendar_id: int
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    csrf_token: str | None = None


class TimeSlotUpdate(BaseModel):
    start_time: str | None = None
    end_time: str | None = None
    csrf_token: str | None = None


class CopyDayBody(BaseModel):
    source_day: int = Field(ge=0, le=6)
    target_days: list[int]
    csrf_token: str | None = None


class PresetWorkweekBody(BaseModel):
    source_day: int = Field(ge=0, le=6)
    csrf_token: str | None = None


class PresetFulltimeBody(BaseModel):
    days: list[int] | None = None
    csrf_token: str | None = None


class DayWorkingBody(BaseModel):
    is_working: bool
    csrf_token: str | None = None


class CalendarSettingsBody(BaseModel):
    break_between_services_minutes: int = 0
    max_services_per_day: int = 0
    book_ahead_hours: int = 24
    reminder_hours_first: int = 0
    reminder_hours_second: int = 0
    reminder_first_enabled: bool = True
    reminder_second_enabled: bool = True
    csrf_token: str | None = None


@router.get("/calendars/{calendar_id}/schedule")
async def get_schedule(calendar_id: int, request: Request, db: Session = Depends(get_db)):
    _, calendar = _require_calendar(request, db, calendar_id)
    return JSONResponse(_schedule_response(calendar, db))


@router.get("/calendars/{calendar_id}/day/{weekday}")
async def get_day(calendar_id: int, weekday: int, request: Request, db: Session = Depends(get_db)):
    if weekday < 0 or weekday > 6:
        raise HTTPException(status_code=400, detail="Некорректный день недели")
    _, calendar = _require_calendar(request, db, calendar_id)
    grouped = slots_by_day(db, calendar.id)
    return JSONResponse(build_day_payload(calendar, grouped, weekday))


@router.post("/time-slots")
async def create_time_slot(body: TimeSlotCreate, request: Request, db: Session = Depends(get_db)):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, calendar = _require_calendar(request, db, body.calendar_id)
    start_t = parse_time_str(body.start_time)
    end_t = parse_time_str(body.end_time)
    if start_t is None or end_t is None:
        raise HTTPException(status_code=400, detail="Некорректное время")
    err = validate_slot_times(start_t, end_t)
    if err:
        raise HTTPException(status_code=400, detail=err)
    slot = TimeSlot(
        calendar_id=calendar.id,
        day_of_week=body.day_of_week,
        start_time=start_t,
        end_time=end_t,
        is_available=True,
    )
    db.add(slot)
    _commit_db(db)
    db.refresh(slot)
    from app.services.calendar_schedule import serialize_slot

    return JSONResponse({
        "slot": serialize_slot(slot),
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "Окно добавлено",
    })


@router.put("/time-slots/{slot_id}")
async def update_time_slot(slot_id: int, body: TimeSlotUpdate, request: Request, db: Session = Depends(get_db)):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    slot = db.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Временное окно не найдено")
    _, calendar = _require_calendar(request, db, slot.calendar_id)
    start_t = parse_time_str(body.start_time) if body.start_time else slot.start_time
    end_t = parse_time_str(body.end_time) if body.end_time else slot.end_time
    if body.start_time and start_t is None:
        raise HTTPException(status_code=400, detail="Некорректное время начала")
    if body.end_time and end_t is None:
        raise HTTPException(status_code=400, detail="Некорректное время окончания")
    err = validate_slot_times(start_t, end_t)
    if err:
        raise HTTPException(status_code=400, detail=err)
    slot.start_time = start_t
    slot.end_time = end_t
    _commit_db(db)
    from app.services.calendar_schedule import serialize_slot

    return JSONResponse({
        "slot": serialize_slot(slot),
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "Окно обновлено",
    })


@router.delete("/time-slots/{slot_id}")
async def remove_time_slot(slot_id: int, request: Request, db: Session = Depends(get_db)):
    token = _csrf_from_request(request)
    if not _json_csrf_ok(request, token):
        raise HTTPException(status_code=403, detail="CSRF")
    slot = db.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Временное окно не найдено")
    _, calendar = _require_calendar(request, db, slot.calendar_id)
    ok, msg = delete_time_slot(db, slot)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return JSONResponse({
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": msg or "Окно удалено",
    })


@router.post("/calendars/{calendar_id}/copy-day")
async def copy_day(calendar_id: int, body: CopyDayBody, request: Request, db: Session = Depends(get_db)):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, calendar = _require_calendar(request, db, calendar_id)
    if body.source_day < 0 or body.source_day > 6:
        raise HTTPException(status_code=400, detail="Некорректный исходный день")
    created = copy_day_slots(db, calendar, body.source_day, body.target_days, replace=True)
    _commit_db(db)
    return JSONResponse({
        "created": created,
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "Расписание скопировано",
    })


@router.post("/calendars/{calendar_id}/copy-week")
async def copy_week(calendar_id: int, body: PresetWorkweekBody, request: Request, db: Session = Depends(get_db)):
    return await preset_workweek_endpoint(calendar_id, body, request, db)


@router.post("/calendars/{calendar_id}/preset/workweek")
async def preset_workweek_endpoint(
    calendar_id: int, body: PresetWorkweekBody, request: Request, db: Session = Depends(get_db)
):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, calendar = _require_calendar(request, db, calendar_id)
    created = preset_workweek(db, calendar, body.source_day)
    _commit_db(db)
    return JSONResponse({
        "created": created,
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "Рабочая неделя создана",
    })


@router.post("/calendars/{calendar_id}/preset/fulltime")
async def preset_fulltime_endpoint(
    calendar_id: int, body: PresetFulltimeBody, request: Request, db: Session = Depends(get_db)
):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, calendar = _require_calendar(request, db, calendar_id)
    created = preset_fulltime(db, calendar, body.days)
    _commit_db(db)
    return JSONResponse({
        "created": created,
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "Режим 24/7 применён",
    })


@router.delete("/calendars/{calendar_id}/day/{weekday}")
async def delete_day_slots(calendar_id: int, weekday: int, request: Request, db: Session = Depends(get_db)):
    token = _csrf_from_request(request)
    if not _json_csrf_ok(request, token):
        raise HTTPException(status_code=403, detail="CSRF")
    if weekday < 0 or weekday > 6:
        raise HTTPException(status_code=400, detail="Некорректный день недели")
    _, calendar = _require_calendar(request, db, calendar_id)
    removed = clear_day_slots(db, calendar.id, weekday)
    _commit_db(db)
    return JSONResponse({
        "removed": removed,
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "День очищен",
    })


@router.patch("/calendars/{calendar_id}/day/{weekday}")
async def patch_day_working(
    calendar_id: int, weekday: int, body: DayWorkingBody, request: Request, db: Session = Depends(get_db)
):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    if weekday < 0 or weekday > 6:
        raise HTTPException(status_code=400, detail="Некорректный день недели")
    _, calendar = _require_calendar(request, db, calendar_id)
    set_day_working(calendar, weekday, body.is_working)
    _commit_db(db)
    grouped = slots_by_day(db, calendar.id)
    return JSONResponse({
        "day": build_day_payload(calendar, grouped, weekday),
        "schedule": _schedule_response(calendar, db, bust=True),
        "message": "Рабочий день обновлён" if body.is_working else "День отмечен как выходной",
    })


@router.put("/calendars/{calendar_id}/settings")
async def update_calendar_settings(
    calendar_id: int, body: CalendarSettingsBody, request: Request, db: Session = Depends(get_db)
):
    if not _json_csrf_ok(request, _csrf_from_request(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, calendar = _require_calendar(request, db, calendar_id)
    calendar.break_between_services_minutes = max(0, body.break_between_services_minutes)
    calendar.max_services_per_day = max(0, body.max_services_per_day)
    calendar.book_ahead_hours = max(0, body.book_ahead_hours)
    calendar.reminder_hours_first = body.reminder_hours_first if body.reminder_first_enabled else 0
    calendar.reminder_hours_second = body.reminder_hours_second if body.reminder_second_enabled else 0
    db.commit()
    from app.services.response_cache import invalidate_calendar

    invalidate_calendar(calendar.id, consultant_id=calendar.consultant_id)
    return JSONResponse({
        "settings": _schedule_response(calendar, db)["settings"],
        "message": "Настройки сохранены",
    })
