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
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value.lstrip('/')}"
