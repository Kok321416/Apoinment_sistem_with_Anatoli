"""Simple in-process rate limiting for sensitive admin actions."""
from __future__ import annotations

from collections import defaultdict
from time import time

_buckets: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, *, max_calls: int, window_sec: int) -> bool:
    """Return True if allowed, False if rate limited."""
    now = time()
    bucket = [t for t in _buckets[key] if now - t < window_sec]
    if len(bucket) >= max_calls:
        _buckets[key] = bucket
        return False
    bucket.append(now)
    _buckets[key] = bucket
    return True


def reset_rate_limit(key: str) -> None:
    _buckets.pop(key, None)
