import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import get_current_user, login_user
from app.config import get_settings
from app.database import get_db
from app.models import SocialAccount, User
from app.services.telegram_auth import consume_completed_login, create_login_request, get_completed_login
from app.templating import page_context, templates

router = APIRouter(prefix="/accounts", tags=["oauth"])
settings = get_settings()


@router.get("/telegram/login/")
async def telegram_login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    process = request.query_params.get("process", "login")
    next_url = request.query_params.get("next", "/")

    if process == "connect":
        if not user:
            return RedirectResponse(f"/login/?next={next_url}", status_code=302)
        req = create_login_request(
            db,
            next_url=next_url,
            process="connect",
            connect_user_id=user.id,
        )
    else:
        if user:
            return RedirectResponse(next_url or "/", status_code=302)
        register_fio = request.session.pop("register_fio", None)
        register_phone = request.session.pop("register_phone", None)
        if process == "signup" and register_fio and register_phone:
            req = create_login_request(
                db,
                next_url=next_url,
                process="signup",
                register_fio=register_fio,
                register_phone=register_phone,
            )
        else:
            req = create_login_request(db, next_url=next_url, process="login")

    bot_username = settings.telegram_bot_username.lstrip("@")
    if not bot_username:
        return templates.TemplateResponse("telegram_login.html", page_context(
            request, db, user,
            error="TELEGRAM_BOT_USERNAME не настроен на сервере.",
            login_token=None,
            bot_url=None,
            next_url=next_url,
        ))

    bot_url = f"https://t.me/{bot_username}?start=login_{req.token}"
    tg_app_url = f"tg://resolve?domain={bot_username}&start=login_{req.token}"
    return templates.TemplateResponse("telegram_login.html", page_context(
        request, db, user,
        login_token=req.token,
        bot_url=bot_url,
        tg_app_url=tg_app_url,
        next_url=next_url,
        error=None,
    ))


@router.get("/telegram/login/status/{token}/")
async def telegram_login_status(token: str, db: Session = Depends(get_db)):
    from app.models import TelegramLoginRequest

    req = db.query(TelegramLoginRequest).filter(TelegramLoginRequest.token == token).first()
    if not req:
        return JSONResponse({"completed": False, "error": "not_found"})
    if req.completed and req.complete_token:
        return JSONResponse({
            "completed": True,
            "redirect": f"/accounts/telegram/complete/{req.complete_token}/",
        })
    if req.expires_at < datetime.utcnow():
        return JSONResponse({"completed": False, "error": "expired"})
    return JSONResponse({"completed": False})


@router.get("/telegram/complete/{complete_token}/")
async def telegram_complete_login(complete_token: str, request: Request, db: Session = Depends(get_db)):
    req = get_completed_login(db, complete_token)
    if not req or not req.user_id:
        return RedirectResponse("/login/?error=telegram_expired", status_code=302)
    user = db.get(User, req.user_id)
    if not user:
        return RedirectResponse("/login/", status_code=302)
    login_user(request, user)
    request.session["show_telegram_welcome"] = True
    consume_completed_login(db, req)
    return RedirectResponse(req.next_url or "/", status_code=302)


@router.get("/confirm-email/{token}/")
async def confirm_email(request: Request, token: str, db: Session = Depends(get_db)):
    from app.services.email_verification import verify_email_token

    user = get_current_user(request, db)
    db_user, err = verify_email_token(db, token)
    if db_user:
        return RedirectResponse("/login/?verified=1&email=" + (db_user.email or ""), status_code=302)
    return templates.TemplateResponse("email_confirm_result.html", page_context(
        request, db, user, error=err, success=False,
    ))


@router.get("/password/set/")
@router.post("/password/set/")
async def set_password_page(request: Request, db: Session = Depends(get_db)):
    from app.auth.passwords import hash_password

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
