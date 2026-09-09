"""Timezone helpers: calendar wall-clock, dual display, absolute start."""
from datetime import date, time
from types import SimpleNamespace

from app.services.site_timezone import (
    booking_starts_at,
    convert_wall_clock,
    format_dual_slot,
    timezone_label,
)


def test_convert_irkutsk_to_moscow():
    # 20:00 Irkutsk (UTC+8) == 15:00 Moscow (UTC+3)
    d, t = convert_wall_clock(
        date(2026, 9, 10),
        time(20, 0),
        from_tz="Asia/Irkutsk",
        to_tz="Europe/Moscow",
    )
    assert t.hour == 15
    assert t.minute == 0
    assert d == date(2026, 9, 10)


def test_booking_starts_at_uses_calendar_timezone():
    cal = SimpleNamespace(timezone="Asia/Irkutsk")
    booking = SimpleNamespace(
        booking_date=date(2026, 9, 10),
        booking_time=time(12, 0),
        calendar=cal,
    )
    start = booking_starts_at(booking)
    assert start is not None
    assert str(start.tzinfo) == "Asia/Irkutsk"
    assert start.hour == 12


def test_format_dual_slot_for_client():
    cal = SimpleNamespace(timezone="Asia/Irkutsk", name="Кабинет", consultant=None)
    booking = SimpleNamespace(
        booking_date=date(2026, 9, 10),
        booking_time=time(20, 0),
        booking_end_time=time(21, 0),
        calendar=cal,
        client_timezone="Europe/Moscow",
        service=None,
    )
    dual = format_dual_slot(booking)
    assert "Иркутск" in dual["tz_label"]
    assert "20:00" in dual["slot_with_tz"]
    assert "15:00" in dual["viewer_slot"]
    assert "Москва" in dual["viewer_slot"]
    assert dual["dual_line"].startswith("у вас:")


def test_timezone_label_short():
    assert timezone_label("Asia/Irkutsk", short=True) == "Иркутск"
    assert "UTC+8" in timezone_label("Asia/Irkutsk")
