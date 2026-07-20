import json
import secrets
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.session import get_current_user, login_user
from app.config import get_settings
from app.database import get_db
from app.auth.session import get_current_user, login_user
from app.models import Category, Consultant, EmailAddress, Integration, SocialAccount, User
from app.services.bookings import parse_fio
from app.services.email_verification import verify_email_token
from app.templating import page_context, templates

router = APIRouter(prefix="/accounts", tags=["oauth"])
settings = get_settings()


def _google_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=["openid", "email", "profile"],
    )


@router.get("/google/login/")
async def google_login(request: Request):
    redirect_uri = f"{settings.site_url}/accounts/google/login/callback/"
    flow = _google_flow(redirect_uri)
    flow.redirect_uri = redirect_uri
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = request.query_params.get("next", "/")
    request.session["oauth_process"] = request.query_params.get("process", "login")
    authorization_url, _ = flow.authorization_url(access_type="online", state=state)
    return RedirectResponse(authorization_url, status_code=302)


@router.get("/google/login/callback/")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    if request.query_params.get("error"):
        return RedirectResponse("/login/", status_code=302)
    state = request.query_params.get("state")
    if not state or state != request.session.get("oauth_state"):
        return RedirectResponse("/login/", status_code=302)
    redirect_uri = f"{settings.site_url}/accounts/google/login/callback/"
    flow = _google_flow(redirect_uri)
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=request.query_params.get("code"))
    credentials = flow.credentials
    import httpx
    resp = httpx.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {credentials.token}"},
    )
    info = resp.json()
    email = info.get("email", "")
    google_id = str(info.get("id", ""))
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            username=email, email=email,
            password=hash_password(secrets.token_urlsafe(32)),
            first_name=info.get("given_name", ""),
            last_name=info.get("family_name", ""),
            is_active=True, date_joined=datetime.utcnow(),
        )
        db.add(user)
        db.flush()
    social = db.query(SocialAccount).filter(SocialAccount.provider == "google", SocialAccount.uid == google_id).first()
    if not social:
        db.add(SocialAccount(provider="google", uid=google_id, user_id=user.id, extra_data=json.dumps(info)))
    if request.session.get("oauth_process") == "signup":
        fio = request.session.pop("register_fio", None)
        phone = request.session.pop("register_phone", None)
        if fio and phone and not db.query(Consultant).filter(Consultant.user_id == user.id).first():
            first_name, last_name, middle_name = parse_fio(fio)
            category = db.query(Category).filter(Category.name_category == "Общая").first()
            if not category:
                category = Category(name_category="Общая")
                db.add(category)
                db.flush()
            db.add(Consultant(
                user_id=user.id, first_name=first_name, last_name=last_name,
                middle_name=middle_name, email=email, phone=phone,
                telegram_nickname="", category_of_specialist_id=category.id,
            ))
    db.commit()
    login_user(request, user)
    next_url = request.session.pop("oauth_next", "/")
    return RedirectResponse(next_url, status_code=302)


@router.get("/confirm-email/{token}/")
async def confirm_email(request: Request, token: str, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    db_user, err = verify_email_token(db, token)
    if db_user:
        return RedirectResponse("/login/?verified=1&email=" + (db_user.email or ""), status_code=302)
    return templates.TemplateResponse("email_confirm_result.html", page_context(
        request, db, user, error=err, success=False,
    ))


@router.get("/telegram/login/")
async def telegram_login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    bot_username = settings.telegram_bot_username.lstrip("@")
    return templates.TemplateResponse("telegram_login.html", page_context(
        request, db, user, telegram_bot_username=bot_username,
        next_url=request.query_params.get("next", "/"),
        process=request.query_params.get("process", "login"),
    ))


@router.post("/telegram/login/callback/")
async def telegram_callback(request: Request, db: Session = Depends(get_db)):
    import hashlib
    import hmac
    form = await request.form()
    data = dict(form)
    received_hash = data.pop("hash", "")
    if not received_hash:
        return RedirectResponse("/login/", status_code=302)
    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return RedirectResponse("/login/", status_code=302)
    telegram_id = str(data.get("id", ""))
    username = data.get("username", "")
    first_name = data.get("first_name", "")
    user = db.query(SocialAccount).filter(SocialAccount.provider == "telegram", SocialAccount.uid == telegram_id).first()
    if user:
        db_user = db.get(User, user.user_id)
    else:
        uname = f"telegram_{telegram_id}"
        db_user = db.query(User).filter(User.username == uname).first()
        if not db_user:
            db_user = User(
                username=uname, email=f"{uname}@telegram.user",
                password="!", first_name=first_name, is_active=True,
                date_joined=datetime.utcnow(),
            )
            db.add(db_user)
            db.flush()
        db.add(SocialAccount(provider="telegram", uid=telegram_id, user_id=db_user.id, extra_data=json.dumps(data)))
        db.commit()
    if request.session.get("register_fio") and request.session.get("register_phone"):
        fio = request.session.pop("register_fio")
        phone = request.session.pop("register_phone")
        if not db.query(Consultant).filter(Consultant.user_id == db_user.id).first():
            fn, ln, mn = parse_fio(fio)
            category = db.query(Category).filter(Category.name_category == "Общая").first()
            if not category:
                category = Category(name_category="Общая")
                db.add(category)
                db.flush()
            consultant = Consultant(
                user_id=db_user.id, first_name=fn, last_name=ln, middle_name=mn,
                email=db_user.email or "", phone=phone, telegram_nickname=username,
                category_of_specialist_id=category.id,
            )
            db.add(consultant)
            db.flush()
            integration = Integration(consultant_id=consultant.id, telegram_chat_id=telegram_id, telegram_connected=True, telegram_enabled=True)
            db.add(integration)
    else:
        consultant = db.query(Consultant).filter(Consultant.user_id == db_user.id).first()
        if consultant:
            integration = db.query(Integration).filter(Integration.consultant_id == consultant.id).first()
            if not integration:
                integration = Integration(consultant_id=consultant.id)
                db.add(integration)
            integration.telegram_chat_id = telegram_id
            integration.telegram_connected = True
            integration.telegram_enabled = True
    db.commit()
    request.session["show_telegram_welcome"] = True
    login_user(request, db_user)
    next_url = request.query_params.get("next", "/")
    return RedirectResponse(next_url, status_code=302)


@router.get("/password/set/")
@router.post("/password/set/")
async def set_password_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    if user.has_usable_password:
        return RedirectResponse("/", status_code=302)
    error = None
    if request.method == "POST":
        form = await request.form()
        p1 = form.get("password1", "")
        p2 = form.get("password2", "")
        if p1 != p2:
            error = "Пароли не совпадают"
        elif len(p1) < 8:
            error = "Пароль должен быть не менее 8 символов"
        else:
            db_user = db.get(User, user.id)
            db_user.password = hash_password(p1)
            db.commit()
            next_url = request.query_params.get("next", "/")
            return RedirectResponse(next_url, status_code=302)
    return templates.TemplateResponse("password_set.html", page_context(request, db, user, error=error))


@router.get("/social/connections/")
async def social_connections(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    accounts = db.query(SocialAccount).filter(SocialAccount.user_id == user.id).all()
    return templates.TemplateResponse("social_connections.html", page_context(request, db, user, social_accounts=accounts))
