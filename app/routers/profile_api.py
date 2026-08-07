"""Profile hub REST API (AsyncSession)."""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import get_current_user_async
from app.config import get_settings
from app.database import get_async_db
from app.deps import get_consultant_async, normalize_url, require_specialist_mode_async
from app.models import EmailAddress, SocialAccount
from app.security.csrf import validate_csrf_token
from app.services.profile_hub import apply_profile_fields, build_profile_payload_async
from app.services.public_client import ensure_public_slug_async
from app.services.response_cache import invalidate_profile

router = APIRouter(tags=["profile-api"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _csrf_ok(request: Request, token: str | None) -> bool:
    return validate_csrf_token(request, token)


async def _profile_context(request: Request, db: AsyncSession, user):
    consultant = await require_specialist_mode_async(request, db, user)
    connected = {
        sa.provider
        for sa in (
            await db.execute(select(SocialAccount).where(SocialAccount.user_id == user.id))
        ).scalars().all()
    }
    primary = (
        await db.execute(
            select(EmailAddress).where(
                EmailAddress.user_id == user.id,
                EmailAddress.primary.is_(True),
            )
        )
    ).scalar_one_or_none()
    from app.services.yandex_auth import yandex_oauth_configured

    return await build_profile_payload_async(
        db,
        consultant,
        user,
        connected_providers=connected,
        primary_email=primary.email if primary else consultant.email,
        primary_email_verified=bool(primary and primary.verified),
        has_usable_password=user.has_usable_password,
        yandex_oauth_enabled=yandex_oauth_configured(),
    )


class ProfileUpdateBody(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram_nickname: str | None = None
    profile_description: str | None = None
    video_link: str | None = None
    social_instagram: str | None = None
    social_facebook: str | None = None
    social_vk: str | None = None
    social_telegram: str | None = None
    social_youtube: str | None = None
    website: str | None = None
    csrf_token: str | None = None


@router.get("/profile/data")
async def get_profile_data(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return JSONResponse(await _profile_context(request, db, user))


@router.put("/profile/data")
async def update_profile_data(
    body: ProfileUpdateBody,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    token = request.headers.get("X-CSRF-Token") or body.csrf_token
    if not _csrf_ok(request, token):
        raise HTTPException(status_code=403, detail="CSRF")
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    consultant = await get_consultant_async(db, user)
    apply_profile_fields(consultant, body.model_dump(exclude={"csrf_token"}), normalize_url)
    try:
        await ensure_public_slug_async(db, consultant)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Почта уже используется другим аккаунтом")
    invalidate_profile(consultant.id, user.id)
    from app.templating import clear_header_cache

    clear_header_cache(request)
    return JSONResponse(
        {"message": "Профиль сохранён", "data": await _profile_context(request, db, user)}
    )


@router.post("/profile/avatar")
async def upload_avatar(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    profile_photo: UploadFile = File(...),
):
    token = request.headers.get("X-CSRF-Token")
    if not _csrf_ok(request, token):
        raise HTTPException(status_code=403, detail="CSRF")
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    consultant = await get_consultant_async(db, user)
    from app.routers.pages import _save_profile_photo

    err = await _save_profile_photo(consultant, profile_photo)
    if err:
        raise HTTPException(status_code=400, detail=err)
    await db.commit()
    invalidate_profile(consultant.id, user.id)
    from app.templating import clear_header_cache

    clear_header_cache(request)
    return JSONResponse(
        {"message": "Фото обновлено", "data": await _profile_context(request, db, user)}
    )


@router.get("/profile/preview")
async def get_profile_preview(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await _profile_context(request, db, user)
    return JSONResponse(data["preview"])


@router.get("/profile/completion")
async def get_profile_completion(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await _profile_context(request, db, user)
    return JSONResponse(data["completeness"])


@router.get("/profile/qrcode")
async def profile_qrcode(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await _profile_context(request, db, user)
    url = data["profile"]["public_url"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(url, safe='')}"
    return RedirectResponse(qr_url, status_code=302)
