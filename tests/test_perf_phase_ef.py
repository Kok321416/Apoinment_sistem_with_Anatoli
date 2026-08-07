"""Phase E/F: indexes list + perf metrics smoke."""
from __future__ import annotations

from app.services.perf_metrics import record_request, reset_for_tests, snapshot
from app.services.query_explain import HOT_QUERIES, list_expected_indexes


def test_expected_indexes_cover_hot_paths():
    names = {row["name"] for row in list_expected_indexes()}
    assert "ix_bookings_calendar_date_status" in names
    assert "ix_bookings_telegram_id" in names
    assert "ix_time_slots_calendar_dow" in names
    assert "ix_socialaccount_provider_uid" in names
    assert "ix_calendars_consultant_active" in names
    assert len(HOT_QUERIES) >= 6


def test_perf_metrics_records_and_normalizes_paths():
    reset_for_tests()
    record_request(path="/booking/", status_code=200, duration_ms=12.5, slow_ms=500)
    record_request(path="/booking/42/", status_code=200, duration_ms=800.0, slow_ms=500)
    record_request(path="/api/auth/login", status_code=500, duration_ms=30.0, slow_ms=500)
    snap = snapshot(top_n=10)
    assert snap["requests"] == 3
    assert snap["errors_5xx"] == 1
    assert snap["slow_requests"] == 1
    paths = {p["path"]: p for p in snap["top_paths"]}
    assert "/booking/" in paths or "/booking/{id}/" in paths
    assert paths.get("/booking/{id}/", paths.get("/booking/"))["slow"] >= 1
    reset_for_tests()


def test_notify_bridge_and_reminders_async_import():
    from app.services.notify_bridge import (
        schedule_on_booking_created,
        schedule_rescheduled,
        schedule_status_changed,
    )
    from app.services.telegram import send_reminders_async

    assert callable(schedule_on_booking_created)
    assert callable(schedule_status_changed)
    assert callable(schedule_rescheduled)
    assert callable(send_reminders_async)


def test_alembic_phase_e_revision_chain():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "alembic" / "versions"

    def _load(name: str):
        path = root / name
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return mod

    m1 = _load("001_async_phase_ab_indexes.py")
    m2 = _load("002_async_phase_e_indexes.py")
    assert m1.revision == "001_async_phase_ab"
    assert m2.down_revision == m1.revision
    assert m2.revision == "002_async_phase_e"
