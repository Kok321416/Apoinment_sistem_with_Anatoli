"""VK OAuth helpers and messaging fallback."""
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.telegram_copy import format_client_booked_message
from app.services.vk_auth import generate_pkce_pair, vk_oauth_configured
from app.services.vk_messages import notify_client_booked_vk, tg_html_to_plain


def _booking(*, vk_user_id=111, telegram_id=None, email="c@example.com"):
    consultant = SimpleNamespace(first_name="Иван", last_name="П", email="i@t.c")
    calendar = SimpleNamespace(name="Основной", consultant=consultant)
    service = SimpleNamespace(name="Консультация", duration_minutes=60)
    return SimpleNamespace(
        telegram_id=telegram_id,
        vk_user_id=vk_user_id,
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


def test_pkce_pair_shape():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert "=" not in challenge


def test_vk_oauth_configured_requires_client_id(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "vk_oauth_client_id", "")
    assert vk_oauth_configured() is False
    monkeypatch.setattr(settings, "vk_oauth_client_id", "12345")
    assert vk_oauth_configured() is True


def test_vk_booked_message_plain():
    b = _booking()
    text = tg_html_to_plain(format_client_booked_message(b, channel="vk"))
    assert "Ваша запись подтверждена" in text
    assert "<b>" not in text
    assert "сообщениях VK" in text


def test_notify_client_booked_vk_calls_api():
    b = _booking(vk_user_id=42)
    with patch("app.services.vk_messages.send_vk_message", return_value=True) as mock_send:
        assert notify_client_booked_vk(b) is True
        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == 42
        assert "Ваша запись подтверждена" in mock_send.call_args.args[1]


def test_on_booking_created_prefers_vk_over_email():
    from app.services import telegram as tg

    b = _booking(vk_user_id=99, telegram_id=None)
    b.calendar = SimpleNamespace(consultant=SimpleNamespace(integration=None))
    db = MagicMock()
    with (
        patch.object(tg, "notify_specialist_new_booking"),
        patch("app.services.vk_messages.notify_client_booked_vk", return_value=True) as mock_vk,
        patch("app.services.booking_email.notify_client_via_email_if_no_telegram") as mock_mail,
        patch("app.services.google_calendar.sync_booking_to_google"),
    ):
        tg.on_booking_created(db, b)
        mock_vk.assert_called_once_with(b)
        mock_mail.assert_not_called()
