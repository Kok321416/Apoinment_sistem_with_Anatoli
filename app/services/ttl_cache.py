"""Process-local TTL cache for expensive read-only JSON payloads.

Safe on shared hosting: reduces MySQL work without Redis.
Each Passenger worker has its own memory; short TTL + explicit invalidate keep data fresh.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any, Callable


class TtlCache:
    def __init__(self, *, default_ttl: float = 45.0, max_entries: int = 512):
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
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
        expires_at = time.monotonic() + max(1.0, float(ttl))
        with self._lock:
            if len(self._data) >= self.max_entries and key not in self._data:
                self._evict_expired_unlocked()
            if len(self._data) >= self.max_entries and key not in self._data:
                # Drop oldest expiry first
                oldest = min(self._data.items(), key=lambda kv: kv[1][0])[0]
                self._data.pop(oldest, None)
            self._data[key] = (expires_at, copy.deepcopy(value))

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                self._data.pop(k, None)
            return len(keys)

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


# Shared app cache (one per process / Passenger worker)
CACHE = TtlCache(default_ttl=45.0, max_entries=512)
