from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.session import AuthUser, get_current_user
from app.database import get_db
from app.models import Consultant


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> AuthUser | None:
    return get_current_user(request, db)


def require_user(request: Request, db: Session = Depends(get_db)) -> AuthUser:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login/"})
    return user


def get_consultant(db: Session, user: AuthUser) -> Consultant:
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
    if not consultant:
        raise HTTPException(status_code=302, headers={"Location": "/"})
    return consultant


def normalize_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value or value.lower() in ("none", "null"):
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value.lstrip('/')}"


def blank_field(value: str | None) -> str:
    """Hide empty DB values and literal 'None' strings in form fields."""
    text = (value or "").strip()
    if not text or text.lower() in ("none", "null"):
        return ""
    return text


def normalize_phone(phone: str | None) -> str:
    """Store phone in E.164-ish form that fits consultants.phone (max 15 chars)."""
    raw = (phone or "").strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    if raw.startswith("+") and len(raw) <= 15:
        return raw
    if digits:
        normalized = f"+{digits}"
        return normalized[:15]
    return raw[:15]
