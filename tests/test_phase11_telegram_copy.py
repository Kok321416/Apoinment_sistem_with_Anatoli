"""Phase 11: canonical Telegram copy, HTML escape, no long dashes."""
from datetime import date, datetime, time
from types import SimpleNamespace

from app.services.telegram_copy import (
    assert_no_long_dashes,
    format_broadcast_message,
    format_client_booked_message,
    format_new_booking_message_for_specialist,
    format_reminder_message,
    normalize_dashes,
    sample_template_previews,
    tg_escape,
)


def _booking():
    consultant = SimpleNamespace(first_name="Иван", last_name="П", email="i@t.c")
    calendar = SimpleNamespace(name="Основной", consultant=consultant)
    service = SimpleNamespace(name="Консультация <script>", duration_minutes=60)
    return SimpleNamespace(
        client_name='Вася & "друг"',
        client_phone="+7999",
        client_telegram="@test",
        client_email="a@b.c",
        booking_date=date(2026, 7, 22),
        booking_time=time(15, 0),
        booking_end_time=time(16, 0),
        service=service,
        calendar=calendar,
    )


def test_tg_escape_and_dashes():
    assert tg_escape("a <b> & c") == "a &lt;b&gt; &amp; c"
    assert normalize_dashes("a—b–c") == "a-b-c"
    assert assert_no_long_dashes("a-b")
    assert not assert_no_long_dashes("a—b")


def test_transactional_templates_escape_and_role_titles():
    b = _booking()
    client_msg = format_client_booked_message(b)
    assert "Ваша запись подтверждена" in client_msg
    assert "&lt;script&gt;" in client_msg
    assert assert_no_long_dashes(client_msg)

    spec_msg = format_new_booking_message_for_specialist(b)
    assert "К вам новая запись" in spec_msg
    assert "Вася &amp;" in spec_msg or "Вася" in spec_msg
    assert assert_no_long_dashes(spec_msg)

    rem = format_reminder_message(b, 6)
    assert "Ваша запись: напоминание" in rem
    assert assert_no_long_dashes(rem)


def test_broadcast_envelope():
    assert format_broadcast_message("Привет").startswith("📢")
    already = "📢 Уже с заголовком\n\nТекст"
    assert format_broadcast_message(already) == already
    assert "Новости сервиса" in format_broadcast_message("Анонс")


def test_sample_previews_have_no_long_dashes():
    for item in sample_template_previews():
        assert assert_no_long_dashes(item["text"])
        assert item["title"]
