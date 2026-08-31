"""Bind ops-alert chat_id when the operator messages the bot."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class OpsAlertBindMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user and event.chat:
            try:
                from app.services.ops_alerts import maybe_bind_ops_alert_chat

                maybe_bind_ops_alert_chat(event.chat.id, event.from_user.username)
            except Exception:
                pass
        return await handler(event, data)
