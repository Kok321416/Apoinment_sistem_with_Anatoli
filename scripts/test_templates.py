"""Smoke-test: compile all page templates with minimal context."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datetime import date, datetime, time
from types import SimpleNamespace

from starlette.requests import Request

from app.templating import page_context, templates


class FakeSession(dict):
    def pop(self, key, default=None):
        return super().pop(key, default)


def fake_request():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "session": FakeSession(),
    }
    return Request(scope)


def fake_user():
    return SimpleNamespace(id=1, username="test@example.com", email="test@example.com", is_authenticated=True)


def minimal_context(template_name: str):
    req = fake_request()
    user = fake_user()
    consultant = SimpleNamespace(
        id=1,
        first_name="Test",
        last_name="User",
        email="test@example.com",
        phone="",
        telegram_nickname="",
        profile_photo="",
        profile_description="",
        video_link="",
    )
    calendar = SimpleNamespace(
        id=1,
        name="Cal",
        is_active=True,
        break_between_services_minutes=0,
        book_ahead_hours=24,
        max_services_per_day=0,
        reminder_hours_first=24,
        reminder_hours_second=1,
        created_at=datetime.now(),
    )
    service = SimpleNamespace(id=1, name="Svc", description="Desc", duration_minutes=60, price=100, is_active=True, created_at=datetime.now())
    booking = SimpleNamespace(
        id=1,
        booking_date=date.today(),
        booking_time=time(10, 0),
        booking_end_time=time(11, 0),
        client_name="Client",
        client_phone="+7999",
        client_email="c@example.com",
        client_telegram="",
        notes="",
        status="pending",
        link_token="abc",
        calendar=calendar,
        service=service,
    )
    calendar.time_slots_count = 1
    slot = SimpleNamespace(id=1, start_time=time(9, 0), end_time=time(10, 0))
    card = SimpleNamespace(id=1, name="Card", email="", phone="", telegram="", notes="")
    base = page_context(req, db=None, user=user)
    extras = {
        "profile.html": dict(consultant=consultant, connected_providers=[], primary_email="", success="", error=""),
        "calendars.html": dict(calendars=[calendar], calendars_with_links=[{"calendar": calendar, "booking_url": "https://x/book/1/"}], success="", error=""),
        "calendar_detail.html": dict(
            calendar=calendar,
            time_slots_by_day=[[slot], [], [], [], [], [], []],
            days_names=["Пн"] * 7,
            days_short=["П"] * 7,
            success="",
            error="",
        ),
        "calendar_settings_edit.html": dict(calendar=calendar, success="", error=""),
        "services.html": dict(services=[service], success="", error=""),
        "booking.html": dict(
            upcoming_bookings=[booking],
            past_bookings=[],
            status_filter="all",
            calendar_events=[],
        ),
        "client_cards_list.html": dict(cards=[card], success="", error=""),
        "client_card_detail.html": dict(card=card, bookings=[booking], total_bookings=1, completed_count=0, success="", error=""),
        "integrations.html": dict(
            integration=SimpleNamespace(
                telegram_connected=False,
                telegram_enabled=False,
                telegram_chat_id="",
            ),
            success="",
            error="",
        ),
        "public_booking.html": dict(
            calendar=calendar,
            services=[service],
            available_dates=[],
            selected_date=None,
            slots=[],
            step=1,
            contact_name="",
            contact_phone="",
            contact_telegram="",
            contact_email="",
            booking_client_name="",
            booking_client_phone="",
            error="",
        ),
        "booking_success.html": dict(booking=booking, calendar=calendar, service=service),
        "login.html": dict(error="", next_url="/"),
        "register.html": dict(error="", fio="", phone="", email=""),
    }
    ctx = {**base, **extras.get(template_name, {})}
    return ctx


def main():
    errors = []
    for path in sorted((ROOT / "app" / "templates").glob("*.html")):
        name = path.name
        try:
            templates.env.get_template(name).render(minimal_context(name))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        print("FAILED:")
        for e in errors:
            print(" ", e)
        sys.exit(1)
    print(f"OK: {len(list((ROOT / 'app' / 'templates').glob('*.html')))} templates")


if __name__ == "__main__":
    main()
