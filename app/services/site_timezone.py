"""Timezone helpers: site default, calendar wall-clock, dual display."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.config import get_settings

# Friendly labels for known IANA zones used by the product.
_TZ_LABELS = {
    "Asia/Irkutsk": "Иркутск (UTC+8)",
    "Europe/Moscow": "Москва (UTC+3)",
    "Asia/Yekaterinburg": "Екатеринбург (UTC+5)",
    "Asia/Novosibirsk": "Новосибирск (UTC+7)",
    "Asia/Vladivostok": "Владивосток (UTC+10)",
    "UTC": "UTC",
}

# Choices for calendar settings UI (value, label).
CALENDAR_TIMEZONE_CHOICES: list[tuple[str, str]] = [
    ("Asia/Irkutsk", "Иркутск (UTC+8)"),
    ("Europe/Moscow", "Москва (UTC+3)"),
    ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
    ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
    ("Asia/Vladivostok", "Владивосток (UTC+10)"),
]

_DEFAULT = "Asia/Irkutsk"


def site_timezone_name() -> str:
    return _normalize_tz_name(get_settings().timezone) or _DEFAULT


def site_zoneinfo() -> ZoneInfo:
    return _zoneinfo(site_timezone_name())


def site_timezone_label(*, short: bool = False) -> str:
    return timezone_label(site_timezone_name(), short=short)


def site_timezone_hint() -> str:
    return f"Время указано по часовому поясу: {site_timezone_label()}."


def normalize_timezone_name(name: str | None) -> str:
    """Return valid IANA name or empty string."""
    raw = (name or "").strip()
    if not raw:
        return ""
    try:
        ZoneInfo(raw)
        return raw
    except Exception:
        return ""


def _normalize_tz_name(name: str | None) -> str:
    return normalize_timezone_name(name)


def _zoneinfo(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(_DEFAULT)


def timezone_label(name: str | None, *, short: bool = False) -> str:
    """Human label (e.g. «Иркутск (UTC+8)» or «Иркутск»)."""
    key = _normalize_tz_name(name) or site_timezone_name()
    full = _TZ_LABELS.get(key)
    if not full:
        city = key.split("/")[-1].replace("_", " ")
        full = city
    if short:
        return full.split(" (")[0]
    return full


def calendar_timezone_name(calendar) -> str:
    """Wall-clock zone for a calendar's slots (falls back to site TIMEZONE)."""
    raw = getattr(calendar, "timezone", None) if calendar is not None else None
    return _normalize_tz_name(raw) or site_timezone_name()


def calendar_zoneinfo(calendar) -> ZoneInfo:
    return _zoneinfo(calendar_timezone_name(calendar))


def calendar_timezone_label(calendar, *, short: bool = False) -> str:
    return timezone_label(calendar_timezone_name(calendar), short=short)


def calendar_timezone_hint(calendar) -> str:
    return (
        f"Время приёма указано по часовому поясу специалиста: "
        f"{calendar_timezone_label(calendar)}."
    )


def booking_starts_at(booking) -> datetime | None:
    """Absolute start instant from wall-clock date/time in calendar timezone."""
    if not booking or not booking.booking_date or not booking.booking_time:
        return None
    tz = calendar_zoneinfo(getattr(booking, "calendar", None))
    return datetime.combine(booking.booking_date, booking.booking_time, tzinfo=tz)


def format_wall_clock(d: date | None, t: time | None) -> str:
    if not d or not t:
        return "-"
    return f"{d.strftime('%d.%m.%Y')} {t.strftime('%H:%M')}"


def convert_wall_clock(
    d: date,
    t: time,
    *,
    from_tz: str,
    to_tz: str,
) -> tuple[date, time] | None:
    """Convert a naive wall-clock from one IANA zone to another."""
    src = _normalize_tz_name(from_tz)
    dst = _normalize_tz_name(to_tz)
    if not src or not dst:
        return None
    if src == dst:
        return d, t
    try:
        instant = datetime.combine(d, t, tzinfo=_zoneinfo(src))
        local = instant.astimezone(_zoneinfo(dst))
        return local.date(), local.time().replace(microsecond=0)
    except Exception:
        return None


def format_dual_slot(
    booking,
    *,
    viewer_tz: str | None = None,
) -> dict[str, str]:
    """
    Build display strings for specialist (calendar) time and optional viewer local time.
    Returns keys: slot, slot_with_tz, tz_label, viewer_slot, viewer_tz_label, dual_line.
    """
    cal = getattr(booking, "calendar", None)
    cal_name = calendar_timezone_name(cal)
    cal_label = timezone_label(cal_name, short=True)
    cal_label_full = timezone_label(cal_name)

    time_str = booking.booking_time.strftime("%H:%M") if booking.booking_time else "-"
    end_str = booking.booking_end_time.strftime("%H:%M") if booking.booking_end_time else ""
    slot = f"{time_str}" + (f" - {end_str}" if end_str else "")
    slot_with_tz = f"{slot} ({cal_label})" if slot != "-" else slot

    viewer = _normalize_tz_name(viewer_tz) or _normalize_tz_name(
        getattr(booking, "client_timezone", None)
    )
    viewer_slot = ""
    viewer_tz_label = ""
    dual_line = ""
    if viewer and viewer != cal_name and booking.booking_date and booking.booking_time:
        converted = convert_wall_clock(
            booking.booking_date,
            booking.booking_time,
            from_tz=cal_name,
            to_tz=viewer,
        )
        if converted:
            _vd, vt = converted
            end_local = ""
            if booking.booking_end_time:
                end_c = convert_wall_clock(
                    booking.booking_date,
                    booking.booking_end_time,
                    from_tz=cal_name,
                    to_tz=viewer,
                )
                if end_c:
                    end_local = f" - {end_c[1].strftime('%H:%M')}"
            viewer_tz_label = timezone_label(viewer, short=True)
            viewer_slot = f"{vt.strftime('%H:%M')}{end_local} ({viewer_tz_label})"
            dual_line = f"у вас: {viewer_slot}"

    return {
        "slot": slot,
        "slot_with_tz": slot_with_tz,
        "tz_label": cal_label_full,
        "tz_label_short": cal_label,
        "viewer_slot": viewer_slot,
        "viewer_tz_label": viewer_tz_label,
        "dual_line": dual_line,
    }
