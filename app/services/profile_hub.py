"""Profile hub: serialization, completeness, dashboard stats."""
from __future__ import annotations

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

ABOUT_MIN_CHARS = 30
ABOUT_FULL_CHARS = 80
SOCIAL_LINKS_FOR_FULL = 2


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


def _text(value: str | None) -> str:
    text = (value or "").strip()
    if text.lower() in ("none", "null"):
        return ""
    return text


def _about_points(description: str | None) -> tuple[int, bool, str]:
    length = len(_text(description))
    if length >= ABOUT_FULL_CHARS:
        return 20, True, f"Описание ({length} симв.)"
    if length >= ABOUT_MIN_CHARS:
        return 10, False, f"Описание ({length} из {ABOUT_FULL_CHARS} симв.)"
    return 0, False, f"Описание (от {ABOUT_MIN_CHARS} симв.)"


def _social_points(social_count: int) -> tuple[int, bool, str]:
    if social_count >= SOCIAL_LINKS_FOR_FULL:
        return 15, True, f"Соцсети ({social_count} из {len(SOCIAL_FIELDS)})"
    if social_count == 1:
        return 8, False, f"Соцсети (1 из {SOCIAL_LINKS_FOR_FULL}, нужна ещё 1)"
    return 0, False, f"Соцсети (0 из {SOCIAL_LINKS_FOR_FULL})"


def _completion_message(percent: int) -> str:
    if percent >= 90:
        return "Профиль готов для клиентов"
    if percent >= 70:
        return "Профиль почти готов"
    if percent >= 40:
        return "Хороший старт — добавьте ещё несколько блоков"
    return "Заполните профиль, чтобы клиентам было проще записаться"


def _service_counts(db: Session, consultant_id: int) -> tuple[int, int]:
    svc_total = db.query(func.count(Service.id)).filter(Service.consultant_id == consultant_id).scalar() or 0
    svc_active = (
        db.query(func.count(Service.id))
        .filter(Service.consultant_id == consultant_id, Service.is_active.is_(True))
        .scalar()
    ) or 0
    return svc_total, svc_active


def _calendar_counts(db: Session, consultant_id: int) -> tuple[int, int]:
    cal_total = db.query(func.count(Calendar.id)).filter(Calendar.consultant_id == consultant_id).scalar() or 0
    cal_active = (
        db.query(func.count(Calendar.id))
        .filter(Calendar.consultant_id == consultant_id, Calendar.is_active.is_(True))
        .scalar()
    ) or 0
    return cal_total, cal_active


def compute_completeness(
    *,
    first_name: str | None,
    last_name: str | None,
    email: str | None,
    phone: str | None,
    profile_description: str | None,
    video_link: str | None,
    has_photo: bool,
    social_count: int,
    services_active: int,
    services_total: int,
    calendars_active: int,
    calendars_total: int,
) -> dict:
    checks: list[dict] = []
    score = 0

    name_ok = bool(_text(first_name)) and bool(_text(last_name))
    name_points = 10 if name_ok else 0
    score += name_points
    checks.append({
        "id": "name",
        "label": "Имя и фамилия",
        "tab": "basic",
        "weight": 10,
        "points": name_points,
        "done": name_ok,
    })

    contacts_ok = bool(_text(email)) and bool(_text(phone))
    contacts_points = 10 if contacts_ok else 0
    score += contacts_points
    checks.append({
        "id": "contacts",
        "label": "Email и телефон",
        "tab": "basic",
        "weight": 10,
        "points": contacts_points,
        "done": contacts_ok,
    })

    photo_points = 15 if has_photo else 0
    score += photo_points
    checks.append({
        "id": "photo",
        "label": "Фото профиля",
        "tab": "photo",
        "weight": 15,
        "points": photo_points,
        "done": has_photo,
    })

    about_points, about_done, about_label = _about_points(profile_description)
    score += about_points
    checks.append({
        "id": "about",
        "label": about_label,
        "tab": "about",
        "weight": 20,
        "points": about_points,
        "done": about_done,
        "partial": about_points > 0 and not about_done,
    })

    video_ok = bool(_text(video_link))
    video_points = 5 if video_ok else 0
    score += video_points
    checks.append({
        "id": "video",
        "label": "Видео-презентация",
        "tab": "video",
        "weight": 5,
        "points": video_points,
        "done": video_ok,
    })

    social_points, social_done, social_label = _social_points(social_count)
    score += social_points
    checks.append({
        "id": "social",
        "label": social_label,
        "tab": "social",
        "weight": 15,
        "points": social_points,
        "done": social_done,
        "partial": social_points > 0 and not social_done,
    })

    services_done = services_active > 0
    services_points = 15 if services_done else 0
    score += services_points
    checks.append({
        "id": "services",
        "label": f"Активные услуги ({services_active} из {services_total})",
        "tab": None,
        "weight": 15,
        "points": services_points,
        "done": services_done,
    })

    calendar_done = calendars_active > 0
    calendar_points = 10 if calendar_done else 0
    score += calendar_points
    checks.append({
        "id": "calendar",
        "label": f"Активный календарь ({calendars_active} из {calendars_total})",
        "tab": None,
        "weight": 10,
        "points": calendar_points,
        "done": calendar_done,
    })

    percent = min(score, 100)
    missing = [c["label"] for c in checks if not c["done"]]
    return {
        "percent": percent,
        "message": _completion_message(percent),
        "checks": checks,
        "missing": missing[:4],
        "total_weight": 100,
    }


def completeness(consultant: Consultant, db: Session, consultant_id: int) -> dict:
    svc_total, svc_active = _service_counts(db, consultant_id)
    cal_total, cal_active = _calendar_counts(db, consultant_id)
    return compute_completeness(
        first_name=consultant.first_name,
        last_name=consultant.last_name,
        email=consultant.email,
        phone=consultant.phone,
        profile_description=consultant.profile_description,
        video_link=consultant.video_link,
        has_photo=bool(consultant.profile_photo),
        social_count=connected_social_count(consultant),
        services_active=svc_active,
        services_total=svc_total,
        calendars_active=cal_active,
        calendars_total=cal_total,
    )


def completion_meta(consultant: Consultant, db: Session, consultant_id: int) -> dict:
    svc_total, svc_active = _service_counts(db, consultant_id)
    cal_total, cal_active = _calendar_counts(db, consultant_id)
    return {
        "has_photo": bool(consultant.profile_photo),
        "services_active": svc_active,
        "services_total": svc_total,
        "calendars_active": cal_active,
        "calendars_total": cal_total,
        "about_min_chars": ABOUT_MIN_CHARS,
        "about_full_chars": ABOUT_FULL_CHARS,
        "social_links_for_full": SOCIAL_LINKS_FOR_FULL,
        "social_fields": list(SOCIAL_FIELDS),
    }


def dashboard_stats(db: Session, consultant_id: int) -> dict:
    svc_total, svc_active = _service_counts(db, consultant_id)
    cal_total, cal_active = _calendar_counts(db, consultant_id)
    clients = db.query(func.count(ClientCard.id)).filter(ClientCard.consultant_id == consultant_id).scalar() or 0
    return {
        "services_total": svc_total,
        "services_active": svc_active,
        "calendars_total": cal_total,
        "calendars_active": cal_active,
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
        "completion_meta": completion_meta(consultant, db, consultant.id),
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
