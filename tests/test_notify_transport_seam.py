"""Every booking notify path must deliver through send_telegram_message.

When cancel notifications moved from the fire-and-forget thread to a blocking send, the dedup tests
kept patching the old function: they passed while asserting on deliveries that no longer happened.
These tests fail loudly if a notify path stops going through the single transport seam, or if a new
ad-hoc sendMessage caller appears in the module.
"""
from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.services.telegram as tg

TELEGRAM_MODULE = Path(tg.__file__)


@pytest.fixture()
def deliveries(monkeypatch):
    """Record deliveries through the seam; nothing else may reach the network."""
    recorded: list[dict] = []

    def fake_send(chat_id, text, bot_token=None, **kwargs):
        recorded.append({"chat_id": str(chat_id), "text": text, "token": bot_token, **kwargs})
        return True

    def fail_on_direct_http(*_args, **_kwargs):
        raise AssertionError("notify path bypassed send_telegram_message and built its own request")

    monkeypatch.setattr(tg, "send_telegram_message", fake_send)
    monkeypatch.setattr(tg, "_send_message_request", fail_on_direct_http)
    return recorded


def _booking(*, client_tg="200", specialist_chat="100", status="confirmed"):
    integration = SimpleNamespace(
        telegram_connected=True,
        telegram_enabled=True,
        telegram_chat_id=specialist_chat,
        telegram_bot_token=None,
    )
    return SimpleNamespace(
        id=41,
        status=status,
        telegram_id=client_tg,
        calendar=SimpleNamespace(
            name="Кабинет",
            consultant=SimpleNamespace(
                first_name="Иван",
                last_name="П",
                email="a@b.c",
                integration=integration,
            ),
        ),
        client_name="Клиент",
        client_phone="+79990000000",
        client_telegram="",
        client_email="",
        service=SimpleNamespace(name="Услуга", duration_minutes=30),
        booking_date=date.today(),
        booking_time=time(12, 0),
        booking_end_time=None,
    )


def test_status_change_delivers_through_seam(deliveries, monkeypatch):
    monkeypatch.setattr(tg, "notify_dedup_enabled", lambda: False)

    tg.notify_booking_status_changed(MagicMock(), _booking(status="cancelled"), old_status="pending")

    assert [d["chat_id"] for d in deliveries] == ["200", "100"]


def test_specialist_new_booking_delivers_through_seam(deliveries):
    assert tg.notify_specialist_new_booking(_booking()) is True
    assert [d["chat_id"] for d in deliveries] == ["100"]


def test_reschedule_delivers_through_seam(deliveries, monkeypatch):
    monkeypatch.setattr(tg, "notify_dedup_enabled", lambda: False)
    booking = _booking()

    tg.notify_booking_rescheduled(MagicMock(), booking, old_date=date.today(), old_time=time(9, 0))

    assert {d["chat_id"] for d in deliveries} == {"200", "100"}


def test_client_helper_tags_recipient_type(deliveries):
    assert tg.send_telegram_to_client(200, "hi", booking_id=7) is True
    assert deliveries == [
        {"chat_id": "200", "text": "hi", "token": None, "booking_id": 7, "recipient_type": "client"}
    ]


def test_fire_and_forget_submits_the_same_seam(monkeypatch):
    submitted = {}

    monkeypatch.setattr(
        tg._tg_executor,
        "submit",
        lambda fn, *args, **kwargs: submitted.update(fn=fn, args=args, kwargs=kwargs),
    )

    tg.send_telegram_async("100", "hi", recipient_type="specialist")

    assert submitted["fn"] is tg.send_telegram_message


def test_send_message_url_is_built_in_one_place():
    source = TELEGRAM_MODULE.read_text(encoding="utf-8")
    builders = [
        line.strip()
        for line in source.splitlines()
        if re.search(r"api\.telegram\.org.+sendMessage", line)
    ]
    assert len(builders) == 1, (
        "sendMessage requests must be built only in _send_message_request; found:\n  "
        + "\n  ".join(builders)
    )
