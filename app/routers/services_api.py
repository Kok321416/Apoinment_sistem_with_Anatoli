"""REST API for services catalog."""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.session import get_current_user
from app.database import get_db
from app.deps import require_specialist_mode
from app.models import Booking, Calendar, Service, User
from app.security.csrf import validate_csrf_token
from app.services.entity_delete import delete_service
from app.services.services_catalog import (
    booking_counts,
    build_catalog_payload,
    next_sort_order,
    serialize_service,
    service_statistics,
)

router = APIRouter(tags=["services-api"])
logger = logging.getLogger(__name__)


def _csrf_ok(request: Request, token: str | None) -> bool:
    return validate_csrf_token(request, token)


def _csrf_token(request: Request, data: dict | None = None) -> str | None:
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token
    if data:
        return data.get("csrf_token")
    return None


def _require_consultant(request: Request, db: Session) -> tuple[User, int]:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    consultant = require_specialist_mode(request, db, user)
    return user, consultant.id


def _get_service(db: Session, consultant_id: int, service_id: int) -> Service:
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.consultant_id == consultant_id)
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    return service


def _parse_price(raw) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _catalog(db: Session, consultant_id: int) -> dict:
    return build_catalog_payload(db, consultant_id)


class ServiceCreateBody(BaseModel):
    name: str
    description: str = ""
    duration_minutes: int = Field(default=60, ge=15)
    price: float | None = None
    calendar_id: int
    color: str = "#7d5cff"
    icon: str | None = None
    is_active: bool = True
    csrf_token: str | None = None


class ServiceUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=15)
    price: float | None = None
    calendar_id: int | None = None
    color: str | None = None
    icon: str | None = None
    is_active: bool | None = None
    csrf_token: str | None = None


class BulkBody(BaseModel):
    service_ids: list[int]
    action: str
    calendar_id: int | None = None
    color: str | None = None
    is_active: bool | None = None
    csrf_token: str | None = None


class ReorderBody(BaseModel):
    order: list[int]
    csrf_token: str | None = None


@router.get("/services/catalog")
async def get_catalog(request: Request, db: Session = Depends(get_db)):
    _, consultant_id = _require_consultant(request, db)
    return JSONResponse(_catalog(db, consultant_id))


@router.get("/services/{service_id}")
async def get_service(service_id: int, request: Request, db: Session = Depends(get_db)):
    _, consultant_id = _require_consultant(request, db)
    service = _get_service(db, consultant_id, service_id)
    counts = booking_counts(db, [service.id])
    return JSONResponse(serialize_service(service, counts.get(service.id, 0)))


@router.post("/services/new")
async def create_service(body: ServiceCreateBody, request: Request, db: Session = Depends(get_db)):
    if not _csrf_ok(request, _csrf_token(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, consultant_id = _require_consultant(request, db)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название услуги")
    calendar = (
        db.query(Calendar)
        .filter(Calendar.id == body.calendar_id, Calendar.consultant_id == consultant_id)
        .first()
    )
    if not calendar:
        raise HTTPException(status_code=400, detail="Выберите календарь")
    service = Service(
        consultant_id=consultant_id,
        calendar_id=calendar.id,
        name=name,
        description=body.description or "",
        duration_minutes=body.duration_minutes,
        price=_parse_price(body.price),
        color=body.color or "#7d5cff",
        icon=body.icon,
        is_active=body.is_active,
        sort_order=next_sort_order(db, consultant_id),
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return JSONResponse({
        "service": serialize_service(service, 0),
        "catalog": _catalog(db, consultant_id),
        "message": "Услуга создана",
    })


@router.put("/services/{service_id}")
async def update_service(
    service_id: int, body: ServiceUpdateBody, request: Request, db: Session = Depends(get_db)
):
    if not _csrf_ok(request, _csrf_token(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, consultant_id = _require_consultant(request, db)
    service = _get_service(db, consultant_id, service_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Укажите название услуги")
        service.name = name
    if body.description is not None:
        service.description = body.description
    if body.duration_minutes is not None:
        service.duration_minutes = body.duration_minutes
    if body.price is not None:
        service.price = _parse_price(body.price)
    if body.calendar_id is not None:
        calendar = (
            db.query(Calendar)
            .filter(Calendar.id == body.calendar_id, Calendar.consultant_id == consultant_id)
            .first()
        )
        if not calendar:
            raise HTTPException(status_code=400, detail="Выберите календарь")
        service.calendar_id = calendar.id
    if body.color is not None:
        service.color = body.color
    if body.icon is not None:
        service.icon = body.icon
    if body.is_active is not None:
        service.is_active = body.is_active
    db.commit()
    db.refresh(service)
    counts = booking_counts(db, [service.id])
    return JSONResponse({
        "service": serialize_service(service, counts.get(service.id, 0)),
        "catalog": _catalog(db, consultant_id),
        "message": "Услуга обновлена",
    })


@router.delete("/services/{service_id}")
async def remove_service(service_id: int, request: Request, db: Session = Depends(get_db)):
    if not _csrf_ok(request, _csrf_token(request)):
        raise HTTPException(status_code=403, detail="CSRF")
    _, consultant_id = _require_consultant(request, db)
    service = _get_service(db, consultant_id, service_id)
    ok, msg = delete_service(db, service)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return JSONResponse({"catalog": _catalog(db, consultant_id), "message": msg or "Услуга удалена"})


@router.post("/services/{service_id}/duplicate")
async def duplicate_service(service_id: int, request: Request, db: Session = Depends(get_db)):
    if not _csrf_ok(request, _csrf_token(request)):
        raise HTTPException(status_code=403, detail="CSRF")
    _, consultant_id = _require_consultant(request, db)
    source = _get_service(db, consultant_id, service_id)
    copy_name = f"{source.name} (копия)"
    existing = (
        db.query(Service)
        .filter(Service.consultant_id == consultant_id, Service.name == copy_name)
        .count()
    )
    if existing:
        copy_name = f"{source.name} (копия {existing + 1})"
    service = Service(
        consultant_id=consultant_id,
        calendar_id=source.calendar_id,
        name=copy_name,
        description=source.description,
        duration_minutes=source.duration_minutes,
        price=source.price,
        color=source.color,
        icon=source.icon,
        is_active=source.is_active,
        sort_order=next_sort_order(db, consultant_id),
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return JSONResponse({
        "service": serialize_service(service, 0),
        "catalog": _catalog(db, consultant_id),
        "message": "Услуга продублирована",
    })


@router.get("/services/{service_id}/statistics")
async def get_service_statistics(service_id: int, request: Request, db: Session = Depends(get_db)):
    _, consultant_id = _require_consultant(request, db)
    service = _get_service(db, consultant_id, service_id)
    return JSONResponse({
        "service": serialize_service(service, 0),
        "statistics": service_statistics(db, service),
    })


@router.post("/services/bulk")
async def bulk_action(body: BulkBody, request: Request, db: Session = Depends(get_db)):
    if not _csrf_ok(request, _csrf_token(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, consultant_id = _require_consultant(request, db)
    if not body.service_ids:
        raise HTTPException(status_code=400, detail="Выберите услуги")
    services = (
        db.query(Service)
        .filter(Service.consultant_id == consultant_id, Service.id.in_(body.service_ids))
        .all()
    )
    if body.action == "toggle":
        for service in services:
            service.is_active = not service.is_active
    elif body.action == "deactivate":
        for service in services:
            service.is_active = False
    elif body.action == "activate":
        for service in services:
            service.is_active = True
    elif body.action == "delete":
        blocked = [
            s.name
            for s in services
            if db.query(Booking).filter(Booking.service_id == s.id).count()
        ]
        if blocked:
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось удалить «{blocked[0]}»: есть связанные записи",
            )
        for service in services:
            db.delete(service)
    elif body.action == "set_calendar":
        if not body.calendar_id:
            raise HTTPException(status_code=400, detail="Укажите календарь")
        calendar = (
            db.query(Calendar)
            .filter(Calendar.id == body.calendar_id, Calendar.consultant_id == consultant_id)
            .first()
        )
        if not calendar:
            raise HTTPException(status_code=400, detail="Календарь не найден")
        for service in services:
            service.calendar_id = calendar.id
    elif body.action == "set_color":
        if not body.color:
            raise HTTPException(status_code=400, detail="Укажите цвет")
        for service in services:
            service.color = body.color
    else:
        raise HTTPException(status_code=400, detail="Неизвестное действие")
    db.commit()
    return JSONResponse({"catalog": _catalog(db, consultant_id), "message": "Изменения применены"})


@router.put("/services/reorder")
async def reorder_services(body: ReorderBody, request: Request, db: Session = Depends(get_db)):
    if not _csrf_ok(request, _csrf_token(request, body.model_dump())):
        raise HTTPException(status_code=403, detail="CSRF")
    _, consultant_id = _require_consultant(request, db)
    for index, service_id in enumerate(body.order):
        service = _get_service(db, consultant_id, service_id)
        service.sort_order = index
    db.commit()
    return JSONResponse({"catalog": _catalog(db, consultant_id), "message": "Порядок сохранён"})
