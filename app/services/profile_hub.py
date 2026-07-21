"""Profile hub: serialization, completeness, dashboard stats."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Calendar, ClientCard, Consultant, Service
from app.services.public_client import ensure_public_slug, specialist_public_url
from app.templating import profile_photo_src

settings = get_settings()

SOCIAL_FIELDS = (
    "social_instagram",
    "social_facebook",
    "social_vk",
    "social_telegram",
    "social_youtube",
    "website",
)


def full_name(consultant: Consultant) -> str:
    parts = [consultant.first_name, consultant.middle_name, consultant.last_name]
    return " ".join(p for p in parts if p).strip() or "Специалист"


def specialization(consultant: Consultant) -> str:
    if consultant.category and consultant.category.name_category:
        return consultant.category.name_category
    return "Специалист"


def social_links(consultant: Consultant) -> dict[str, str | None]:
    return {field: getattr(consultant, field) or None for field in SOCIAL_FIELDS}


def connected_social_count(consultant: Consultant) -> int:
    return sum(1 for field in SOCIAL_FIELDS if getattr(consultant, field))


def completeness(consultant: Consultant, db: Session, consultant_id: int) -> dict:
    checks = []
    score = 0

    if consultant.profile_photo:
        score += 15
        checks.append({"id": "photo", "label": "Фото профиля", "done": True})
    else:
        checks.append({"id": "photo", "label": "Фото профиля", "done": False})

    if (consultant.profile_description or "").strip():
        score += 20
        checks.append({"id": "about", "label": "Описание", "done": True})
    else:
        checks.append({"id": "about", "label": "Описание", "done": False})

    if consultant.video_link:
        score += 10
        checks.append({"id": "video", "label": "Видео", "done": True})
    else:
        checks.append({"id": "video", "label": "Видео", "done": False})

    social_count = connected_social_count(consultant)
    social_done = social_count >= 2
    if social_done:
        score += 15
    checks.append({
        "id": "social",
        "label": f"Соцсети ({social_count} из 6)",
        "done": social_done,
    })

    svc_total = db.query(func.count(Service.id)).filter(Service.consultant_id == consultant_id).scalar() or 0
    svc_active = (
        db.query(func.count(Service.id))
        .filter(Service.consultant_id == consultant_id, Service.is_active.is_(True))
        .scalar()
    ) or 0
    svc_done = svc_active > 0
    if svc_done:
        score += 15
    checks.append({
        "id": "services",
        "label": f"Услуги ({svc_active} из {svc_total})",
        "done": svc_done,
    })

    basic_done = all([
        consultant.first_name,
        consultant.last_name,
        consultant.email,
        consultant.phone,
    ])
    if basic_done:
        score += 15
    checks.append({"id": "basic", "label": "Основные данные", "done": basic_done})

    if consultant.email and consultant.phone:
        score += 10
        checks.append({"id": "contacts", "label": "Контакты", "done": True})
    else:
        checks.append({"id": "contacts", "label": "Контакты", "done": False})

    score = min(score, 100)
    if score >= 90:
        message = "Профиль готов"
    elif score >= 70:
        message = "Профиль почти готов"
    else:
        message = "Заполните профиль для клиентов"

    missing = [c["label"] for c in checks if not c["done"]]
    return {
        "percent": score,
        "message": message,
        "checks": checks,
        "missing": missing[:4],
    }


def dashboard_stats(db: Session, consultant_id: int) -> dict:
    services_total = db.query(func.count(Service.id)).filter(Service.consultant_id == consultant_id).scalar() or 0
    services_active = (
        db.query(func.count(Service.id))
        .filter(Service.consultant_id == consultant_id, Service.is_active.is_(True))
        .scalar()
    ) or 0
    calendars_total = db.query(func.count(Calendar.id)).filter(Calendar.consultant_id == consultant_id).scalar() or 0
    calendars_active = (
        db.query(func.count(Calendar.id))
        .filter(Calendar.consultant_id == consultant_id, Calendar.is_active.is_(True))
        .scalar()
    ) or 0
    clients = db.query(func.count(ClientCard.id)).filter(ClientCard.consultant_id == consultant_id).scalar() or 0
    return {
        "services_total": services_total,
        "services_active": services_active,
        "calendars_total": calendars_total,
        "calendars_active": calendars_active,
        "clients_total": clients,
    }


def serialize_preview(consultant: Consultant, slug: str, db: Session, consultant_id: int) -> dict:
    services = (
        db.query(Service)
        .filter(Service.consultant_id == consultant_id, Service.is_active.is_(True))
        .order_by(Service.sort_order, Service.name)
        .limit(5)
        .all()
    )
    return {
        "full_name": full_name(consultant),
        "specialization": specialization(consultant),
        "photo_url": profile_photo_src(consultant.profile_photo) if consultant.profile_photo else None,
        "description": consultant.profile_description or "",
        "video_link": consultant.video_link or "",
        "social": social_links(consultant),
        "public_url": specialist_public_url(settings.site_url, slug),
        "services": [{"name": s.name, "color": s.color or "#7d5cff"} for s in services],
    }


def build_profile_payload(
    db: Session,
    consultant: Consultant,
    user,
    *,
    connected_providers: set[str],
    primary_email: str,
    primary_email_verified: bool,
    has_usable_password: bool,
    yandex_oauth_enabled: bool,
) -> dict:
    slug = ensure_public_slug(db, consultant)
    comp = completeness(consultant, db, consultant.id)
    dash = dashboard_stats(db, consultant.id)
    dash["completeness"] = comp["percent"]
    return {
        "profile": {
            "id": consultant.id,
            "first_name": consultant.first_name,
            "last_name": consultant.last_name,
            "middle_name": consultant.middle_name or "",
            "email": consultant.email,
            "phone": consultant.phone,
            "telegram_nickname": consultant.telegram_nickname or "",
            "profile_description": consultant.profile_description or "",
            "video_link": consultant.video_link or "",
            "photo_url": profile_photo_src(consultant.profile_photo) if consultant.profile_photo else None,
            "full_name": full_name(consultant),
            "specialization": specialization(consultant),
            "created_at": consultant.created_at.isoformat() if consultant.created_at else None,
            "updated_at": consultant.updated_at.isoformat() if consultant.updated_at else None,
            "public_url": specialist_public_url(settings.site_url, slug),
            "public_slug": slug,
            **social_links(consultant),
        },
        "dashboard": dash,
        "completeness": comp,
        "preview": serialize_preview(consultant, slug, db, consultant.id),
        "auth": {
            "connected_providers": sorted(connected_providers),
            "primary_email": primary_email,
            "primary_email_verified": primary_email_verified,
            "has_usable_password": has_usable_password,
            "yandex_oauth_enabled": yandex_oauth_enabled,
        },
        "footer": {
            "created_at": consultant.created_at.isoformat() if consultant.created_at else None,
            "updated_at": consultant.updated_at.isoformat() if consultant.updated_at else None,
            "consultant_id": consultant.id,
            "timezone": settings.timezone,
            "profile_version": "v2.0",
        },
    }


def apply_profile_fields(consultant: Consultant, data: dict, normalize_url_fn) -> None:
    if "first_name" in data and data["first_name"] is not None:
        consultant.first_name = data["first_name"]
    if "last_name" in data and data["last_name"] is not None:
        consultant.last_name = data["last_name"]
    if "middle_name" in data and data["middle_name"] is not None:
        consultant.middle_name = data["middle_name"]
    if "phone" in data and data["phone"] is not None:
        consultant.phone = data["phone"]
    if "telegram_nickname" in data and data["telegram_nickname"] is not None:
        consultant.telegram_nickname = data["telegram_nickname"]
    if "email" in data and data["email"] is not None:
        consultant.email = data["email"]
    if "profile_description" in data and data["profile_description"] is not None:
        consultant.profile_description = data["profile_description"]
    if "video_link" in data:
        consultant.video_link = normalize_url_fn(data.get("video_link"))
    for field in SOCIAL_FIELDS:
        if field in data:
            consultant.__setattr__(field, normalize_url_fn(data.get(field)))
