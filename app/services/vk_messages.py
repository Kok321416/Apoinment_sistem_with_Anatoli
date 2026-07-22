"""Send booking notifications to VK community messages."""
from __future__ import annotations

import html
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.config import get_settings
from app.models import Booking
from app.services.telegram_copy import (
    format_booking_rescheduled_client,
    format_booking_status_changed_client,
    format_client_booked_message,
    format_reminder_message,
)
from app.services.vk_auth import vk_messaging_configured

logger = logging.getLogger(__name__)
settings = get_settings()

_TAG_RE = re.compile(r"<[^>]+>")
_vk_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vk-send")

VK_API_VERSION = "5.199"
VK_API_URL = "https://api.vk.com/method/messages.send"


def client_has_vk(booking: Booking) -> bool:
    return bool(getattr(booking, "vk_user_id", None))


def tg_html_to_plain(tg_html: str) -> str:
    text = tg_html or ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def send_vk_message(user_id: int, text: str) -> bool:
    """Send a community message to VK user. Requires messages allowed by user."""
    if not vk_messaging_configured():
        logger.warning("VK messaging not configured (VK_GROUP_ID / VK_GROUP_ACCESS_TOKEN)")
        return False
    token = settings.vk_group_access_token
    message = (text or "").strip()
    if not message or not user_id:
        return False
    try:
        response = httpx.post(
            VK_API_URL,
            data={
                "access_token": token,
                "user_id": int(user_id),
                "random_id": random.randint(1, 2_147_483_647),
                "message": message,
                "v": VK_API_VERSION,
            },
            timeout=15,
        )
        payload = response.json()
        if payload.get("error"):
            err = payload["error"]
            logger.warning(
                "VK messages.send error user_id=%s code=%s msg=%s",
                user_id,
                err.get("error_code"),
                err.get("error_msg"),
            )
            return False
        return True
    except Exception:
        logger.exception("VK messages.send failed for user_id=%s", user_id)
        return False


def send_vk_message_async(user_id: int, text: str) -> None:
    _vk_executor.submit(send_vk_message, user_id, text)


def notify_client_booked_vk(booking: Booking) -> bool:
    if not client_has_vk(booking):
        return False
    text = tg_html_to_plain(format_client_booked_message(booking, channel="vk"))
    return send_vk_message(int(booking.vk_user_id), text)


def notify_client_status_vk(booking: Booking, new_status: str, old_status: str | None = None) -> bool:
    if not client_has_vk(booking):
        return False
    text = tg_html_to_plain(format_booking_status_changed_client(booking, new_status, old_status))
    return send_vk_message(int(booking.vk_user_id), text)


def notify_client_reschedule_vk(
    booking: Booking, *, old_date, old_time, old_end_time=None
) -> bool:
    if not client_has_vk(booking):
        return False
    text = tg_html_to_plain(
        format_booking_rescheduled_client(
            booking, old_date=old_date, old_time=old_time, old_end_time=old_end_time
        )
    )
    return send_vk_message(int(booking.vk_user_id), text)


def notify_client_reminder_vk(booking: Booking, hours_ahead: int) -> bool:
    if not client_has_vk(booking):
        return False
    text = tg_html_to_plain(format_reminder_message(booking, hours_ahead))
    return send_vk_message(int(booking.vk_user_id), text)
