"""Short TTL in-memory response cache tests."""
from __future__ import annotations

from app.services.response_cache import (
    catalog_key,
    invalidate_calendar,
    invalidate_consultant,
    invalidate_profile,
    profile_key,
    schedule_key,
)
from app.services.ttl_cache import CACHE, TtlCache


def setup_function():
    CACHE.clear()


def test_ttl_cache_get_set_and_expire(monkeypatch):
    c = TtlCache(default_ttl=10, max_entries=8)
    c.set("a", {"x": 1}, ttl=10)
    assert c.get("a") == {"x": 1}
    # Mutating returned copy must not affect store
    got = c.get("a")
    got["x"] = 99
    assert c.get("a")["x"] == 1

    mono = {"t": 100.0}

    def fake_mono():
        return mono["t"]

    monkeypatch.setattr("app.services.ttl_cache.time.monotonic", fake_mono)
    c.set("b", 2, ttl=5)
    assert c.get("b") == 2
    mono["t"] = 106.0
    assert c.get("b") is None


def test_ttl_cache_get_or_set_calls_factory_once():
    c = TtlCache(default_ttl=30)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return {"ok": True}

    assert c.get_or_set("k", factory) == {"ok": True}
    assert c.get_or_set("k", factory) == {"ok": True}
    assert calls["n"] == 1


def test_invalidate_consultant_clears_catalog_and_profiles():
    CACHE.set(catalog_key(7), {"services": []})
    CACHE.set(profile_key(7, 1), {"profile": {}})
    CACHE.set(profile_key(7, 2), {"profile": {}})
    CACHE.set(catalog_key(8), {"keep": True})
    invalidate_consultant(7)
    assert CACHE.get(catalog_key(7)) is None
    assert CACHE.get(profile_key(7, 1)) is None
    assert CACHE.get(profile_key(7, 2)) is None
    assert CACHE.get(catalog_key(8)) == {"keep": True}


def test_invalidate_calendar_also_bumps_consultant():
    CACHE.set(schedule_key(3), {"week": []})
    CACHE.set(catalog_key(9), {"services": [1]})
    invalidate_calendar(3, consultant_id=9)
    assert CACHE.get(schedule_key(3)) is None
    assert CACHE.get(catalog_key(9)) is None


def test_invalidate_profile_single_user():
    CACHE.set(profile_key(5, 10), {"a": 1})
    CACHE.set(profile_key(5, 11), {"b": 2})
    invalidate_profile(5, 10)
    assert CACHE.get(profile_key(5, 10)) is None
    assert CACHE.get(profile_key(5, 11)) == {"b": 2}
