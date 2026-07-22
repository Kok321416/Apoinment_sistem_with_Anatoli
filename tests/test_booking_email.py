"""Client booking emails when Telegram is not linked."""
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from app.services.booking_email import (
    notify_client_reminder_email,
    notify_client_via_email_if_no_telegram,
)
from app.services.telegram_copy import assert_no_long_dashes, format_client_booked_message


def _booking(*, telegram_id=None, email="client@example.com"):
    consultant = SimpleNamespace(first_name="Иван", last_name="П", email="i@t.c")
    calendar = SimpleNamespace(name="Основной", consultant=consultant)
    service = SimpleNamespace(name="Консультация", duration_minutes=60)
    return SimpleNamespace(
        telegram_id=telegram_id,
        client_name="Анна",
        client_phone="+7999",
        client_telegram="",
        client_email=email,
        booking_date=date(2026, 7, 22),
        booking_time=time(15, 0),
        booking_end_time=time(16, 0),
        service=service,
        calendar=calendar,
    )


def test_email_channel_footer_differs_from_telegram():
    b = _booking()
    tg = format_client_booked_message(b)
    mail = format_client_booked_message(b, channel="email")
    assert "сюда" in tg
    assert "на эту почту" in mail
    assert assert_no_long_dashes(mail)


def test_sends_email_when_no_telegram():
    b = _booking(telegram_id=None)
    with patch("app.services.booking_email.send_email", return_value=True) as mock_send:
        assert notify_client_via_email_if_no_telegram(b) is True
        assert mock_send.called
        args, kwargs = mock_send.call_args
        assert args[0] == "client@example.com"
        assert "Ваша запись подтверждена" in args[1]
        html_body = args[2]
        assert "Ваша запись подтверждена" in html_body
        assert "Консультация" in html_body
        assert "Иван П" in html_body
        assert kwargs.get("template_key") == "booking_client_confirmed"


def test_skips_email_when_telegram_linked():
    b = _booking(telegram_id=12345)
    with patch("app.services.booking_email.send_email") as mock_send:
        assert notify_client_via_email_if_no_telegram(b) is False
        mock_send.assert_not_called()


def test_skips_email_without_address():
    b = _booking(telegram_id=None, email="")
    with patch("app.services.booking_email.send_email") as mock_send:
        assert notify_client_via_email_if_no_telegram(b) is False
        mock_send.assert_not_called()


def test_reminder_email_when_no_telegram():
    b = _booking(telegram_id=None)
    with patch("app.services.booking_email.send_email", return_value=True) as mock_send:
        assert notify_client_reminder_email(b, 6) is True
        assert "напоминание" in mock_send.call_args.args[1].lower()
        assert mock_send.call_args.kwargs.get("template_key") == "booking_client_reminder"


def test_on_booking_created_falls_back_to_email():
    from app.services import telegram as tg

    b = _booking(telegram_id=None)
    b.calendar = SimpleNamespace(consultant=SimpleNamespace(integration=None))
    db = SimpleNamespace()
    with (
        patch.object(tg, "notify_specialist_new_booking"),
        patch("app.services.booking_email.notify_client_via_email_if_no_telegram") as mock_mail,
        patch("app.services.google_calendar.sync_booking_to_google"),
    ):
        tg.on_booking_created(db, b)
        mock_mail.assert_called_once_with(b)
