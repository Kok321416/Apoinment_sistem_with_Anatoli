"""Simple in-process rate limiting for abuse prevention.

Not a substitute for edge/WAF DDoS protection, but stops credential stuffing,
signup spam, and request floods hitting the app workers.
"""
from __future__ import annotations

from collections import defaultdict
from time import time

_buckets: dict[str, list[float]] = defaultdict(list)
_MAX_KEYS = 20_000


def check_rate_limit(key: str, *, max_calls: int, window_sec: int) -> bool:
    """Return True if allowed, False if rate limited."""
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
    _buckets.pop(key, None)


def _prune_stale(now: float, *, window_sec: int) -> None:
    stale = [k for k, times in _buckets.items() if not times or now - times[-1] >= window_sec]
    for k in stale[: max(1, len(stale) // 2)]:
        _buckets.pop(k, None)
