"""Domain keys for specialist payload caches + invalidation helpers."""
from __future__ import annotations

from app.services.ttl_cache import CACHE

TTL_SEC = 45.0


def catalog_key(consultant_id: int) -> str:
    return f"svc:catalog:{int(consultant_id)}"


def schedule_key(calendar_id: int) -> str:
    return f"cal:schedule:{int(calendar_id)}"


def profile_key(consultant_id: int, user_id: int) -> str:
    return f"profile:{int(consultant_id)}:{int(user_id)}"


def invalidate_consultant(consultant_id: int) -> None:
    """Drop catalog + all profile payloads for this specialist."""
    CACHE.delete(catalog_key(consultant_id))
    CACHE.delete_prefix(f"profile:{int(consultant_id)}:")


def invalidate_calendar(calendar_id: int, *, consultant_id: int | None = None) -> None:
    CACHE.delete(schedule_key(calendar_id))
    if consultant_id is not None:
        invalidate_consultant(consultant_id)


def invalidate_profile(consultant_id: int, user_id: int | None = None) -> None:
    if user_id is not None:
        CACHE.delete(profile_key(consultant_id, user_id))
    else:
        CACHE.delete_prefix(f"profile:{int(consultant_id)}:")
