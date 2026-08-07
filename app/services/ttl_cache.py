"""Process-local TTL cache for expensive read-only JSON payloads.

Uses Redis when REDIS_URL is set and reachable; otherwise in-process memory.
Each Passenger worker still has local memory; Redis shares keys across workers.
"""
from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any, Callable

from app.services.redis_client import redis_delete, redis_delete_prefix, redis_get, redis_set


class TtlCache:
    def __init__(self, *, default_ttl: float = 45.0, max_entries: int = 512, redis_prefix: str = "ayc:ttl:"):
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self.redis_prefix = redis_prefix
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def _rkey(self, key: str) -> str:
        return f"{self.redis_prefix}{key}"

    def get(self, key: str) -> Any | None:
        raw = redis_get(self._rkey(key))
        if raw is not None:
            try:
                return json.loads(raw)
            except Exception:
                pass
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at < now:
                self._data.pop(key, None)
                return None
            return copy.deepcopy(value)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = self.default_ttl if ttl is None else ttl
        ttl_i = max(1, int(ttl))
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            if redis_set(self._rkey(key), payload, ttl_sec=ttl_i):
                return
        except Exception:
            pass
        expires_at = time.monotonic() + max(1.0, float(ttl))
        with self._lock:
            if len(self._data) >= self.max_entries and key not in self._data:
                self._evict_expired_unlocked()
            if len(self._data) >= self.max_entries and key not in self._data:
                oldest = min(self._data.items(), key=lambda kv: kv[1][0])[0]
                self._data.pop(oldest, None)
            self._data[key] = (expires_at, copy.deepcopy(value))

    def delete(self, key: str) -> None:
        redis_delete(self._rkey(key))
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        n = redis_delete_prefix(self._rkey(prefix))
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                self._data.pop(k, None)
            return n + len(keys)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: float | None = None) -> Any:
        hit = self.get(key)
        if hit is not None:
            return hit
        value = factory()
        self.set(key, value, ttl=ttl)
        return copy.deepcopy(value)

    def _evict_expired_unlocked(self) -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._data.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)


# Shared app cache (one per process / Passenger worker; Redis when configured)
CACHE = TtlCache(default_ttl=45.0, max_entries=512)
