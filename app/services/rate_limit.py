"""Rate limiting with optional Redis backend.

Without Redis: per-process buckets (same as before).
With Redis: shared sliding window across workers.
"""
from __future__ import annotations

from collections import defaultdict
from time import time

from app.services.redis_client import get_redis

_buckets: dict[str, list[float]] = defaultdict(list)
_MAX_KEYS = 20_000


def check_rate_limit(key: str, *, max_calls: int, window_sec: int) -> bool:
    """Return True if allowed, False if rate limited."""
    client = get_redis()
    if client is not None:
        try:
            rkey = f"ayc:rl:{key}"
            now = time()
            pipe = client.pipeline()
            pipe.zremrangebyscore(rkey, 0, now - window_sec)
            pipe.zcard(rkey)
            _removed, count = pipe.execute()
            if int(count) >= max_calls:
                return False
            pipe = client.pipeline()
            pipe.zadd(rkey, {f"{now:.6f}": now})
            pipe.expire(rkey, window_sec + 1)
            pipe.execute()
            return True
        except Exception:
            pass

    now = time()
    if len(_buckets) > _MAX_KEYS:
        _prune_stale(now, window_sec=max(window_sec, 300))
    bucket = [t for t in _buckets[key] if now - t < window_sec]
    if len(bucket) >= max_calls:
        _buckets[key] = bucket
        return False
    bucket.append(now)
    _buckets[key] = bucket
    return True


def reset_rate_limit(key: str) -> None:
    client = get_redis()
    if client is not None:
        try:
            client.delete(f"ayc:rl:{key}")
        except Exception:
            pass
    _buckets.pop(key, None)


def _prune_stale(now: float, *, window_sec: int) -> None:
    stale = [k for k, times in _buckets.items() if not times or now - times[-1] >= window_sec]
    for k in stale[: max(1, len(stale) // 2)]:
        _buckets.pop(k, None)
