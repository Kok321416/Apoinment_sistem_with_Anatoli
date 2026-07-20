import logging
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.auth.session import get_current_user
from app.config import get_settings
from app.database import get_db
from app.deps import get_consultant
from app.models import Consultant, Integration

router = APIRouter(tags=["integrations-oauth"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/integrations/google/connect/")
async def google_calendar_connect(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    consultant = get_consultant(db, user)
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return RedirectResponse("/integrations/", status_code=302)
    redirect_uri = f"{settings.site_url}/integrations/google/callback"
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=settings.google_calendar_scopes,
    )
    flow.redirect_uri = redirect_uri
    authorization_url, state = flow.authorization_url(access_type="offline", prompt="consent", state=str(consultant.id))
    request.session["google_calendar_oauth_state"] = state
    return RedirectResponse(authorization_url, status_code=302)


@router.get("/integrations/google/callback")
async def google_calendar_callback(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    if request.query_params.get("error"):
        request.session["integrations_error"] = "Доступ к Google Calendar не был предоставлен."
        return RedirectResponse("/integrations/", status_code=302)
    code = request.query_params.get("code")
    state_from_google = request.query_params.get("state")
    state_stored = request.session.get("google_calendar_oauth_state")
    if not code or not state_stored or state_from_google != state_stored:
        request.session["integrations_error"] = "Неверный ответ от Google."
        return RedirectResponse("/integrations/", status_code=302)
    try:
        consultant = db.get(Consultant, int(state_stored))
        if not consultant or consultant.user_id != user.id:
            request.session["integrations_error"] = "Доступ запрещён."
            return RedirectResponse("/integrations/", status_code=302)
    except (ValueError, TypeError):
        request.session["integrations_error"] = "Сессия истекла."
        return RedirectResponse("/integrations/", status_code=302)
    redirect_uri = f"{settings.site_url}/integrations/google/callback"
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=settings.google_calendar_scopes,
    )
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code)
    credentials = flow.credentials
    integration = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
    if not integration:
        integration = Integration(consultant_id=consultant.id)
        db.add(integration)
    integration.google_refresh_token = credentials.refresh_token or ""
    integration.google_calendar_id = integration.google_calendar_id or "primary"
    integration.google_calendar_connected = True
    integration.google_calendar_enabled = True
    db.commit()
    request.session.pop("google_calendar_oauth_state", None)
    request.session["integrations_success"] = "Google Calendar успешно подключён."
    return RedirectResponse("/integrations/", status_code=302)
