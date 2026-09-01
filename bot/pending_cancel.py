"""Pending specialist booking cancellation: wait for free-text reason in Telegram."""
from __future__ import annotations

_pending: dict[str, dict] = {}


def set_pending_cancel(chat_id, booking_id: int, *, message_id: int | None = None) -> None:
    _pending[str(chat_id)] = {
        "booking_id": int(booking_id),
        "message_id": int(message_id) if message_id is not None else None,
    }


def get_pending_cancel(chat_id) -> dict | None:
    return _pending.get(str(chat_id))


def clear_pending_cancel(chat_id) -> dict | None:
    return _pending.pop(str(chat_id), None)
