"""Lightweight request metrics (Phase F) with optional Redis multi-worker rollup."""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_REDIS_PREFIX = "perf:v1:"
_REDIS_TTL = 86400


@dataclass
class _PathStats:
    count: int = 0
    errors: int = 0
    slow: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0


@dataclass
class PerfRegistry:
    started_at: float = field(default_factory=time.time)
    requests: int = 0
    errors: int = 0
    slow: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    by_path: dict[str, _PathStats] = field(default_factory=lambda: defaultdict(_PathStats))


_REG = PerfRegistry()


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    if path.startswith("/static/"):
        return "/static/…"
    if path.startswith("/media/"):
        return "/media/…"
    parts = []
    for p in path.strip("/").split("/"):
        if not p:
            continue
        if p.isdigit() or (len(p) >= 24 and all(c.isalnum() or c in "-_" for c in p)):
            parts.append("{id}")
        else:
            parts.append(p)
    normalized = "/" + "/".join(parts)
    if path.endswith("/") and parts:
        normalized += "/"
    return normalized or "/"


def _redis_record(key: str, *, duration_ms: float, is_err: bool, is_slow: bool) -> None:
    from app.services.redis_client import get_redis

    client = get_redis()
    if not client:
        return
    try:
        pipe = client.pipeline()
        g = f"{_REDIS_PREFIX}global"
        p = f"{_REDIS_PREFIX}path:{key}"
        for rk in (g, p):
            pipe.hincrby(rk, "requests", 1)
            pipe.hincrbyfloat(rk, "total_ms", float(duration_ms))
            if is_err:
                pipe.hincrby(rk, "errors", 1)
            if is_slow:
                pipe.hincrby(rk, "slow", 1)
            pipe.expire(rk, _REDIS_TTL)
        pipe.execute()
        # approximate max outside the incr pipeline
        for rk in (g, p):
            cur = client.hget(rk, "max_ms")
            if cur is None or float(cur) < duration_ms:
                client.hset(rk, "max_ms", f"{duration_ms:.3f}")
                client.expire(rk, _REDIS_TTL)
    except Exception:
        logger.exception("perf redis_record failed")


def record_request(*, path: str, status_code: int, duration_ms: float, slow_ms: float) -> None:
    key = _normalize_path(path)
    is_err = status_code >= 500
    is_slow = duration_ms >= slow_ms
    with _LOCK:
        _REG.requests += 1
        _REG.total_ms += duration_ms
        if duration_ms > _REG.max_ms:
            _REG.max_ms = duration_ms
        if is_err:
            _REG.errors += 1
        if is_slow:
            _REG.slow += 1
        st = _REG.by_path[key]
        st.count += 1
        st.total_ms += duration_ms
        if duration_ms > st.max_ms:
            st.max_ms = duration_ms
        if is_err:
            st.errors += 1
        if is_slow:
            st.slow += 1
    try:
        _redis_record(key, duration_ms=duration_ms, is_err=is_err, is_slow=is_slow)
    except Exception:
        logger.exception("perf redis side-effect failed")


def _snapshot_local(*, top_n: int) -> dict:
    req = _REG.requests
    avg = (_REG.total_ms / req) if req else 0.0
    paths = sorted(
        (
            {
                "path": path,
                "count": st.count,
                "errors": st.errors,
                "slow": st.slow,
                "avg_ms": round(st.total_ms / st.count, 2) if st.count else 0.0,
                "max_ms": round(st.max_ms, 2),
            }
            for path, st in _REG.by_path.items()
        ),
        key=lambda x: x["count"],
        reverse=True,
    )[:top_n]
    return {
        "uptime_sec": int(time.time() - _REG.started_at),
        "requests": req,
        "errors_5xx": _REG.errors,
        "slow_requests": _REG.slow,
        "avg_ms": round(avg, 2),
        "max_ms": round(_REG.max_ms, 2),
        "top_paths": paths,
        "source": "memory",
    }


def _snapshot_redis(*, top_n: int) -> dict | None:
    from app.services.redis_client import get_redis

    client = get_redis()
    if not client:
        return None
    try:
        g = client.hgetall(f"{_REDIS_PREFIX}global") or {}
        if not g:
            return None
        req = int(float(g.get("requests") or 0))
        total = float(g.get("total_ms") or 0.0)
        errors = int(float(g.get("errors") or 0))
        slow = int(float(g.get("slow") or 0))
        max_ms = float(g.get("max_ms") or 0.0)
        paths: list[dict] = []
        for key in client.scan_iter(match=f"{_REDIS_PREFIX}path:*", count=200):
            name = str(key).split("path:", 1)[-1]
            h = client.hgetall(key) or {}
            c = int(float(h.get("requests") or 0))
            if not c:
                continue
            t = float(h.get("total_ms") or 0.0)
            paths.append(
                {
                    "path": name,
                    "count": c,
                    "errors": int(float(h.get("errors") or 0)),
                    "slow": int(float(h.get("slow") or 0)),
                    "avg_ms": round(t / c, 2) if c else 0.0,
                    "max_ms": round(float(h.get("max_ms") or 0.0), 2),
                }
            )
        paths.sort(key=lambda x: x["count"], reverse=True)
        return {
            "uptime_sec": int(time.time() - _REG.started_at),
            "requests": req,
            "errors_5xx": errors,
            "slow_requests": slow,
            "avg_ms": round(total / req, 2) if req else 0.0,
            "max_ms": round(max_ms, 2),
            "top_paths": paths[:top_n],
            "source": "redis",
        }
    except Exception:
        logger.exception("perf redis snapshot failed")
        return None


def snapshot(*, top_n: int = 15) -> dict:
    with _LOCK:
        local = _snapshot_local(top_n=top_n)
    redis_snap = _snapshot_redis(top_n=top_n)
    if redis_snap and redis_snap.get("requests", 0) >= local.get("requests", 0):
        return redis_snap
    return local


def reset_for_tests() -> None:
    global _REG
    with _LOCK:
        _REG = PerfRegistry()
