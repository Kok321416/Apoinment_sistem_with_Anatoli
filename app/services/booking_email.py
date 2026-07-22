"""Client booking emails when Telegram is not linked.

Copy mirrors Telegram bot templates (telegram_copy); layout matches site emails.
"""
from __future__ import annotations

import html
import logging
import re

from app.config import get_settings
from app.models import Booking
from app.services.email import send_email
from app.services.telegram_copy import (
    format_booking_rescheduled_client,
    format_booking_status_changed_client,
    format_client_booked_message,
    format_reminder_message,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_TAG_RE = re.compile(r"<[^>]+>")


def client_has_telegram(booking: Booking) -> bool:
    return bool(getattr(booking, "telegram_id", None))


def client_notify_email(booking: Booking) -> str | None:
    email = (getattr(booking, "client_email", None) or "").strip()
    return email or None


def _tg_html_to_plain(tg_html: str) -> str:
    text = tg_html or ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def _tg_html_to_email_inner(tg_html: str) -> str:
    """Keep Telegram <b>/<a>; turn newlines into <br> for HTML mail clients."""
    text = (tg_html or "").replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    for line in text.split("\n"):
        parts.append(line if line else "&nbsp;")
    return "<br>\n".join(parts)


def _wrap_booking_email(*, title: str, tg_html: str) -> tuple[str, str]:
    brand = settings.site_brand_name
    site = settings.site_url.rstrip("/")
    inner = _tg_html_to_email_inner(tg_html)
    plain = _tg_html_to_plain(tg_html)
    html_body = f"""
    <div style="margin:0;padding:0;background:#0b1020;font-family:Segoe UI,Arial,sans-serif;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1020;padding:32px 16px;">
        <tr>
          <td align="center">
            <table role="presentation" width="100%" style="max-width:520px;background:#121826;border:1px solid #2a3348;border-radius:16px;overflow:hidden;">
              <tr>
                <td style="padding:28px 28px 8px;text-align:center;">
                  <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#49d1ff;margin-bottom:12px;">{html.escape(brand)}</div>
                  <h1 style="margin:0;font-size:22px;line-height:1.3;color:#f4f7ff;">{html.escape(title)}</h1>
                </td>
              </tr>
              <tr>
                <td style="padding:12px 28px 8px;color:#f4f7ff;font-size:15px;line-height:1.7;text-align:left;">
                  {inner}
                </td>
              </tr>
              <tr>
                <td style="padding:8px 28px 28px;color:#8b95b0;font-size:13px;line-height:1.5;text-align:center;">
                  Письмо отправлено, потому что Telegram не привязан к этой записи.<br>
                  <a href="{html.escape(site)}" style="color:#49d1ff;text-decoration:none;">{html.escape(site)}</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </div>
    """
    plain_full = f"{plain}\n\nПисьмо отправлено, потому что Telegram не привязан к этой записи.\n{site}\n"
    return html_body, plain_full


def _send_client_booking_mail(
    booking: Booking,
    *,
    subject_title: str,
    tg_html: str,
    template_key: str,
) -> bool:
    to_email = client_notify_email(booking)
    if not to_email:
        return False
    brand = settings.site_brand_name
    subject = f"{subject_title} - {brand}"
    html_body, plain = _wrap_booking_email(title=subject_title, tg_html=tg_html)
    return send_email(to_email, subject, html_body, plain, template_key=template_key)


def notify_client_via_email_if_no_telegram(booking: Booking) -> bool:
    """Send booking confirmation email when client has no telegram_id."""
    if client_has_telegram(booking):
        return False
    try:
        return _send_client_booking_mail(
            booking,
            subject_title="Ваша запись подтверждена",
            tg_html=format_client_booked_message(booking, channel="email"),
            template_key="booking_client_confirmed",
        )
    except Exception:
        logger.exception("Failed to send client booking confirmation email")
        return False


def notify_client_status_email(booking: Booking, new_status: str, old_status: str | None = None) -> bool:
    if client_has_telegram(booking):
        return False
    try:
        return _send_client_booking_mail(
            booking,
            subject_title="Ваша запись: изменение статуса",
            tg_html=format_booking_status_changed_client(booking, new_status, old_status),
            template_key="booking_client_status",
        )
    except Exception:
        logger.exception("Failed to send client booking status email")
        return False


def notify_client_reschedule_email(
    booking: Booking, *, old_date, old_time, old_end_time=None
) -> bool:
    if client_has_telegram(booking):
        return False
    try:
        return _send_client_booking_mail(
            booking,
            subject_title="Ваша запись: перенесена",
            tg_html=format_booking_rescheduled_client(
                booking, old_date=old_date, old_time=old_time, old_end_time=old_end_time
            ),
            template_key="booking_client_reschedule",
        )
    except Exception:
        logger.exception("Failed to send client booking reschedule email")
        return False


def notify_client_reminder_email(booking: Booking, hours_ahead: int) -> bool:
    if client_has_telegram(booking):
        return False
    try:
        return _send_client_booking_mail(
            booking,
            subject_title="Ваша запись: напоминание",
            tg_html=format_reminder_message(booking, hours_ahead),
            template_key="booking_client_reminder",
        )
    except Exception:
        logger.exception("Failed to send client booking reminder email")
        return False
