"""Client diagnostics cabinet + invite links + specialist visibility helpers."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.session import get_current_user_async
from app.database import get_async_db
from app.diagnostics.catalog import get_test, list_tests
from app.models import ClientCard, Consultant, DiagnosticAttempt
from app.security.csrf import validate_csrf_token
from app.services.diagnostics_service import (
    attempt_to_view,
    complete_attempt,
    create_invitation,
    list_attempts_for_card,
    list_attempts_for_client,
    list_client_psychologists,
    resolve_invitation,
    start_attempt,
    touch_client_specialist_link,
)
from app.services.public_client import ensure_public_slug_async
from app.services.specialist_features import FEATURE_DIAGNOSTICS, consultant_has_feature
from app.templating import page_context_async, templates
from app.utils.safe_redirect import login_url_with_next, safe_next_url

router = APIRouter(tags=["diagnostics"])


async def _require_user(request: Request, db: AsyncSession):
    user = await get_current_user_async(request, db)
    if not user:
        return None
    return user


def _login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(login_url_with_next(str(request.url.path) + (("?" + request.url.query) if request.url.query else "")), status_code=302)


async def _redirect_diagnostics_to_profile(db, consultant_id: int, suffix: str = "") -> RedirectResponse | None:
    consultant = (
        await db.execute(select(Consultant).where(Consultant.id == consultant_id))
    ).scalar_one_or_none()
    if not consultant:
        return RedirectResponse("/", status_code=302)
    slug = await ensure_public_slug_async(db, consultant)
    return RedirectResponse(f"/s/{slug}/diagnostics/{suffix}", status_code=302)


@router.get("/diagnostics/")
async def diagnostics_hub(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Legacy client cabinet hub — redirect to specialist profile diagnostics."""
    selected_id = request.query_params.get("consultant_id")
    if selected_id:
        try:
            cid = int(selected_id)
        except ValueError:
            cid = None
        if cid:
            redirect = await _redirect_diagnostics_to_profile(db, cid)
            if redirect:
                return redirect
    user = await _require_user(request, db)
    if user:
        psychologists = await list_client_psychologists(db, user.id)
        if psychologists:
            redirect = await _redirect_diagnostics_to_profile(db, psychologists[0].id)
            if redirect:
                return redirect
    return RedirectResponse("/", status_code=302)


@router.post("/diagnostics/select/")
async def diagnostics_select(request: Request, db: AsyncSession = Depends(get_async_db)):
    form = await request.form()
    try:
        cid = int(form.get("consultant_id") or 0)
    except ValueError:
        cid = 0
    if cid:
        redirect = await _redirect_diagnostics_to_profile(db, cid)
        if redirect:
            return redirect
    return RedirectResponse("/", status_code=302)


@router.get("/diagnostics/tests/{test_code}/")
async def diagnostics_take_test(
    test_code: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    cid = request.session.get("diagnostics_consultant_id")
    try:
        consultant_id = int(request.query_params.get("consultant_id") or cid or 0)
    except ValueError:
        consultant_id = 0
    if consultant_id:
        redirect = await _redirect_diagnostics_to_profile(db, consultant_id, f"tests/{test_code}/")
        if redirect:
            return redirect
    return RedirectResponse("/", status_code=302)


@router.post("/diagnostics/tests/{test_code}/submit/")
async def diagnostics_submit(
    test_code: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    form = await request.form()
    try:
        consultant_id = int(form.get("consultant_id") or 0)
    except ValueError:
        consultant_id = 0
    if consultant_id:
        redirect = await _redirect_diagnostics_to_profile(db, consultant_id, f"tests/{test_code}/")
        if redirect:
            return redirect
    return RedirectResponse("/", status_code=302)


@router.get("/diagnostics/results/{attempt_id}/")
async def diagnostics_result(
    attempt_id: int, request: Request, db: AsyncSession = Depends(get_async_db)
):
    user = await _require_user(request, db)
    if not user:
        return _login_redirect(request)
    attempt = (
        await db.execute(select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
    ).scalar_one_or_none()
    if not attempt or attempt.status != "completed":
        return RedirectResponse("/", status_code=302)

    allowed = attempt.client_user_id == user.id
    if not allowed:
        cons = (
            await db.execute(select(Consultant).where(Consultant.user_id == user.id))
        ).scalar_one_or_none()
        if cons and cons.id == attempt.consultant_id:
            allowed = True
    if not allowed:
        return RedirectResponse("/", status_code=302)

    if attempt.client_user_id == user.id:
        redirect = await _redirect_diagnostics_to_profile(
            db, attempt.consultant_id, f"results/{attempt_id}/"
        )
        if redirect:
            return redirect

    view = attempt_to_view(attempt)
    show_answers = False
    answers = {}
    cons = (
        await db.execute(select(Consultant).where(Consultant.user_id == user.id))
    ).scalar_one_or_none()
    if cons and cons.id == attempt.consultant_id:
        show_answers = True
        try:
            answers = json.loads(attempt.answers_json or "{}")
        except json.JSONDecodeError:
            answers = {}

    return templates.TemplateResponse(
        "app/diagnostics_result.html",
        await page_context_async(
            request,
            db,
            user,
            cabinet_nav_active="diagnostics",
            result=view,
            attempt=attempt,
            show_answers=show_answers,
            answers=answers,
            test=get_test(attempt.test_code),
        ),
    )


@router.get("/d/{token}/")
async def diagnostics_invite_entry(
    token: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    inv = await resolve_invitation(db, token)
    if not inv:
        return templates.TemplateResponse(
            "app/diagnostics_invite_invalid.html",
            await page_context_async(request, db, None, error="Ссылка недействительна или истекла."),
            status_code=404,
        )
    user = await get_current_user_async(request, db)
    next_path = f"/d/{token}/start/"
    if not user:
        return RedirectResponse(login_url_with_next(next_path), status_code=302)
    return RedirectResponse(next_path, status_code=302)


@router.get("/d/{token}/start/")
async def diagnostics_invite_start(
    token: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    user = await _require_user(request, db)
    if not user:
        return RedirectResponse(login_url_with_next(f"/d/{token}/start/"), status_code=302)
    inv = await resolve_invitation(db, token)
    if not inv:
        return RedirectResponse("/", status_code=302)
    if inv.client_user_id and inv.client_user_id != user.id:
        return RedirectResponse("/", status_code=302)

    await touch_client_specialist_link(
        db, client_user_id=user.id, consultant_id=inv.consultant_id, source="invite"
    )
    inv.use_count = int(inv.use_count or 0) + 1
    if not inv.client_user_id:
        inv.client_user_id = user.id
    await db.commit()
    request.session["diagnostics_invitation_id"] = inv.id

    slug = await ensure_public_slug_async(
        db,
        (await db.execute(select(Consultant).where(Consultant.id == inv.consultant_id))).scalar_one(),
    )
    codes = []
    try:
        codes = json.loads(inv.test_codes_json or "[]")
    except json.JSONDecodeError:
        codes = []
    if codes:
        return RedirectResponse(f"/s/{slug}/diagnostics/tests/{codes[0]}/", status_code=302)
    return RedirectResponse(f"/s/{slug}/diagnostics/", status_code=302)


@router.post("/api/specialist/diagnostics/invite/")
async def api_create_invite(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    cons = (
        await db.execute(select(Consultant).where(Consultant.user_id == user.id))
    ).scalar_one_or_none()
    if not cons or not consultant_has_feature(cons, FEATURE_DIAGNOSTICS):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    card_id = payload.get("client_card_id")
    try:
        card_id_i = int(card_id) if card_id is not None else None
    except (TypeError, ValueError):
        card_id_i = None
    client_user_id = None
    if card_id_i:
        card = (
            await db.execute(
                select(ClientCard).where(
                    ClientCard.id == card_id_i, ClientCard.consultant_id == cons.id
                )
            )
        ).scalar_one_or_none()
        if not card:
            return JSONResponse({"ok": False, "error": "card"}, status_code=404)
        client_user_id = card.client_user_id
    inv, raw = await create_invitation(
        db,
        consultant_id=cons.id,
        created_by_user_id=user.id,
        client_user_id=client_user_id,
        client_card_id=card_id_i,
        test_codes=payload.get("test_codes") or [],
    )
    await db.commit()
    from app.config import get_settings

    base = get_settings().site_url.rstrip("/")
    return JSONResponse({"ok": True, "url": f"{base}/d/{raw}/", "invitation_id": inv.id})
