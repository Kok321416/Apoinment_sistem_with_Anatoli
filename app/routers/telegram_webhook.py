"""Telegram webhook endpoint (aiogram 3) — mounted on FastAPI."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telegram-webhook"])


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    expected = (get_settings().telegram_webhook_secret or "").strip()
    if (
        not expected
        or len(secret) != len(expected)
        or not secrets.compare_digest(secret, expected)
    ):
        raise HTTPException(status_code=403, detail="forbidden")

    from aiogram.types import Update

    from bot.aiogram_app import get_bot, get_dispatcher

    bot = get_bot()
    dp = get_dispatcher()
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return JSONResponse({"ok": True})
