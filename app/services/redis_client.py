"""Optional Redis client with in-memory fallback.

When REDIS_URL is empty or Redis is down, callers fall back to process-local storage.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()
_client_failed = False


def redis_enabled() -> bool:
    return bool((get_settings().redis_url or "").strip())


def get_redis():
    """Return a redis.Redis client or None if unavailable."""
    global _client, _client_failed
    if not redis_enabled() or _client_failed:
        return None
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        if _client_failed:
            return None
        try:
            import redis

            client = redis.Redis.from_url(
                get_settings().redis_url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
            client.ping()
            _client = client
            logger.info("Redis connected: %s", get_settings().redis_url.split("@")[-1])
            return _client
        except Exception as exc:
            _client_failed = True
            logger.warning("Redis unavailable, using in-memory fallback: %s", exc)
            return None


def redis_get(key: str) -> str | None:
    client = get_redis()
    if not client:
        return None
    try:
        return client.get(key)
    except Exception:
        logger.exception("redis_get failed key=%s", key)
        return None


def redis_set(key: str, value: str, *, ttl_sec: int) -> bool:
    client = get_redis()
    if not client:
        return False
    try:
        client.setex(key, max(1, int(ttl_sec)), value)
        return True
    except Exception:
        logger.exception("redis_set failed key=%s", key)
        return False


def redis_delete(key: str) -> None:
    client = get_redis()
    if not client:
        return
    try:
        client.delete(key)
    except Exception:
        logger.exception("redis_delete failed key=%s", key)


def redis_delete_prefix(prefix: str) -> int:
    client = get_redis()
    if not client:
        return 0
    deleted = 0
    try:
        for key in client.scan_iter(match=f"{prefix}*", count=200):
            deleted += int(client.delete(key) or 0)
    except Exception:
        logger.exception("redis_delete_prefix failed prefix=%s", prefix)
    return deleted


def redis_health() -> dict[str, Any]:
    if not redis_enabled():
        return {"configured": False, "ok": False, "mode": "memory"}
    client = get_redis()
    if not client:
        return {"configured": True, "ok": False, "mode": "memory-fallback"}
    try:
        client.ping()
        return {"configured": True, "ok": True, "mode": "redis"}
    except Exception as exc:
        return {"configured": True, "ok": False, "mode": "memory-fallback", "error": str(exc)[:120]}
