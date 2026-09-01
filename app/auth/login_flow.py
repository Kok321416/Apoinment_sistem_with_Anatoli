"""Unified login completion with optional 2FA challenge."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import login_user, login_user_async
from app.models import User
from app.services.admin_totp import needs_admin_2fa, needs_admin_2fa_async, verify_admin_2fa_login, verify_admin_2fa_login_async
from app.services.specialist_totp import (
    needs_specialist_2fa,
    needs_specialist_2fa_async,
    verify_specialist_2fa_login,
    verify_specialist_2fa_login_async,
)
from app.utils.safe_redirect import safe_next_url


def needs_login_2fa(db: Session, user: User) -> bool:
    return needs_admin_2fa(db, user) or needs_specialist_2fa(db, user)


async def needs_login_2fa_async(db, user: User) -> bool:
    return (await needs_admin_2fa_async(db, user)) or (await needs_specialist_2fa_async(db, user))


def verify_login_2fa(db: Session, user: User, code: str) -> bool:
    """Accept code against whichever 2FA factors are enabled for this user."""
    admin_on = needs_admin_2fa(db, user)
    spec_on = needs_specialist_2fa(db, user)
    if not admin_on and not spec_on:
        return True
    ok = False
    if admin_on:
        ok = ok or verify_admin_2fa_login(db, user.id, code)
    if spec_on:
        ok = ok or verify_specialist_2fa_login(db, user.id, code)
    return ok


async def verify_login_2fa_async(db, user: User, code: str) -> bool:
    admin_on = await needs_admin_2fa_async(db, user)
    spec_on = await needs_specialist_2fa_async(db, user)
    if not admin_on and not spec_on:
        return True
    ok = False
    if admin_on:
        ok = ok or await verify_admin_2fa_login_async(db, user.id, code)
    if spec_on:
        ok = ok or await verify_specialist_2fa_login_async(db, user.id, code)
    return ok


def start_2fa_challenge(request: Request, user: User, next_url: str | None) -> RedirectResponse:
    safe = safe_next_url(next_url)
    request.session["pending_2fa_user_id"] = user.id
    request.session["pending_2fa_next"] = safe
    return RedirectResponse(f"/login/2fa/?{urlencode({'next': safe})}", status_code=302)


def finish_login(
    request: Request,
    user: User,
    db: Session,
    next_url: str | None = None,
    *,
    skip_2fa: bool = False,
) -> RedirectResponse:
    """Log in immediately, or park session on 2FA page when required."""
    safe = safe_next_url(next_url)
    if not skip_2fa and needs_login_2fa(db, user):
        return start_2fa_challenge(request, user, safe)
    login_user(request, user, db)
    return RedirectResponse(safe, status_code=302)


async def finish_login_async(
    request: Request,
    user: User,
    db,
    next_url: str | None = None,
    *,
    skip_2fa: bool = False,
) -> RedirectResponse:
    from app.utils.safe_redirect import resolve_post_login_url_async

    safe = await resolve_post_login_url_async(db, user, next_url)
    if not skip_2fa and await needs_login_2fa_async(db, user):
        return start_2fa_challenge(request, user, safe)
    await login_user_async(request, user, db)
    return RedirectResponse(safe, status_code=302)


def finish_login_json(
    request: Request,
    user: User,
    db: Session,
    next_url: str | None = None,
    *,
    skip_2fa: bool = False,
    extra: dict | None = None,
) -> dict:
    """JSON counterpart for API / Mini App auth."""
    safe = safe_next_url(next_url)
    payload = dict(extra or {})
    if not skip_2fa and needs_login_2fa(db, user):
        request.session["pending_2fa_user_id"] = user.id
        request.session["pending_2fa_next"] = safe
        payload.update(
            {
                "success": True,
                "requires_2fa": True,
                "redirect": f"/login/2fa/?{urlencode({'next': safe})}",
            }
        )
        return payload
    login_user(request, user, db)
    payload.update({"success": True, "requires_2fa": False, "redirect": safe})
    return payload


async def finish_login_json_async(
    request: Request,
    user: User,
    db,
    next_url: str | None = None,
    *,
    skip_2fa: bool = False,
    extra: dict | None = None,
) -> dict:
    safe = safe_next_url(next_url)
    payload = dict(extra or {})
    if not skip_2fa and await needs_login_2fa_async(db, user):
        request.session["pending_2fa_user_id"] = user.id
        request.session["pending_2fa_next"] = safe
        payload.update(
            {
                "success": True,
                "requires_2fa": True,
                "redirect": f"/login/2fa/?{urlencode({'next': safe})}",
            }
        )
        return payload
    await login_user_async(request, user, db)
    payload.update({"success": True, "requires_2fa": False, "redirect": safe})
    return payload
