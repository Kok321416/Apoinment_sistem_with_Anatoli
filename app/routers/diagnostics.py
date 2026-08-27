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


@router.get("/diagnostics/")
async def diagnostics_hub(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user(request, db)
    if not user:
        return _login_redirect(request)

    psychologists = await list_client_psychologists(db, user.id)
    selected_id = request.query_params.get("consultant_id")
    selected = None
    if selected_id:
        try:
            sid = int(selected_id)
        except ValueError:
            sid = None
        if sid:
            selected = next((c for c in psychologists if c.id == sid), None)
    if not selected and psychologists:
        selected = psychologists[0]

    attempts = []
    if selected:
        request.session["diagnostics_consultant_id"] = selected.id
        attempts = [
            attempt_to_view(a)
            for a in await list_attempts_for_client(db, client_user_id=user.id, consultant_id=selected.id)
        ]

    tests = list_tests(only_runnable=False)
    return templates.TemplateResponse(
        "app/diagnostics_hub.html",
        await page_context_async(
            request,
            db,
            user,
            cabinet_nav_active="diagnostics",
            psychologists=psychologists,
            selected_consultant=selected,
            tests=tests,
            attempts=attempts,
        ),
    )


@router.post("/diagnostics/select/")
async def diagnostics_select(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await _require_user(request, db)
    if not user:
        return _login_redirect(request)
    form = await request.form()
    if not validate_csrf_token(request, form.get("csrf_token")):
        return RedirectResponse("/diagnostics/?error=csrf", status_code=302)
    try:
        cid = int(form.get("consultant_id") or 0)
    except ValueError:
        cid = 0
    if cid:
        await touch_client_specialist_link(db, client_user_id=user.id, consultant_id=cid, source="manual")
        await db.commit()
        request.session["diagnostics_consultant_id"] = cid
    return RedirectResponse(f"/diagnostics/?consultant_id={cid}", status_code=302)


@router.get("/diagnostics/tests/{test_code}/")
async def diagnostics_take_test(
    test_code: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    user = await _require_user(request, db)
    if not user:
        return _login_redirect(request)
    test = get_test(test_code)
    if not test or not test.runnable:
        return RedirectResponse("/diagnostics/?error=test", status_code=302)

    cid = request.session.get("diagnostics_consultant_id")
    try:
        consultant_id = int(request.query_params.get("consultant_id") or cid or 0)
    except ValueError:
        consultant_id = 0
    consultant = None
    if consultant_id:
        consultant = (
            await db.execute(
                select(Consultant)
                .options(selectinload(Consultant.category))
                .where(Consultant.id == consultant_id)
            )
        ).scalar_one_or_none()
    if not consultant or not consultant_has_feature(consultant, FEATURE_DIAGNOSTICS):
        return RedirectResponse("/diagnostics/?error=specialist", status_code=302)

    return templates.TemplateResponse(
        "app/diagnostics_take.html",
        await page_context_async(
            request,
            db,
            user,
            cabinet_nav_active="diagnostics",
            test=test,
            consultant=consultant,
        ),
    )


@router.post("/diagnostics/tests/{test_code}/submit/")
async def diagnostics_submit(
    test_code: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    user = await _require_user(request, db)
    if not user:
        return _login_redirect(request)
    form = await request.form()
    if not validate_csrf_token(request, form.get("csrf_token")):
        return RedirectResponse("/diagnostics/?error=csrf", status_code=302)
    try:
        consultant_id = int(form.get("consultant_id") or 0)
    except ValueError:
        consultant_id = 0
    if not consultant_id:
        return RedirectResponse("/diagnostics/?error=specialist", status_code=302)

    answers = {}
    for key, val in form.multi_items():
        if key.startswith("i") and key[1:].isdigit():
            answers[key] = val

    try:
        attempt = await start_attempt(
            db,
            client_user_id=user.id,
            consultant_id=consultant_id,
            test_code=test_code,
            source=(form.get("source") or "cabinet").strip() or "cabinet",
            invitation_id=int(form["invitation_id"]) if form.get("invitation_id") else None,
            booking_id=int(form["booking_id"]) if form.get("booking_id") else None,
        )
        await complete_attempt(db, attempt=attempt, answers=answers)
        await touch_client_specialist_link(
            db, client_user_id=user.id, consultant_id=consultant_id, source="manual"
        )
        await db.commit()
    except ValueError:
        await db.rollback()
        return RedirectResponse("/diagnostics/?error=test", status_code=302)
    except Exception:
        await db.rollback()
        return RedirectResponse("/diagnostics/?error=save", status_code=302)

    return RedirectResponse(f"/diagnostics/results/{attempt.id}/", status_code=302)


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
        return RedirectResponse("/diagnostics/", status_code=302)

    # Client owns attempt OR the consultant linked to the attempt
    allowed = attempt.client_user_id == user.id
    if not allowed:
        cons = (
            await db.execute(select(Consultant).where(Consultant.user_id == user.id))
        ).scalar_one_or_none()
        if cons and cons.id == attempt.consultant_id:
            allowed = True
    if not allowed:
        return RedirectResponse("/diagnostics/", status_code=302)

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
        return RedirectResponse("/diagnostics/?error=invite", status_code=302)
    if inv.client_user_id and inv.client_user_id != user.id:
        return RedirectResponse("/diagnostics/?error=invite_user", status_code=302)

    await touch_client_specialist_link(
        db, client_user_id=user.id, consultant_id=inv.consultant_id, source="invite"
    )
    inv.use_count = int(inv.use_count or 0) + 1
    if not inv.client_user_id:
        inv.client_user_id = user.id
    await db.commit()
    request.session["diagnostics_consultant_id"] = inv.consultant_id
    request.session["diagnostics_invitation_id"] = inv.id

    codes = []
    try:
        codes = json.loads(inv.test_codes_json or "[]")
    except json.JSONDecodeError:
        codes = []
    if codes:
        return RedirectResponse(
            f"/diagnostics/tests/{codes[0]}/?consultant_id={inv.consultant_id}",
            status_code=302,
        )
    return RedirectResponse(f"/diagnostics/?consultant_id={inv.consultant_id}", status_code=302)


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
