"""Create Consultant profile for an existing User (become specialist / specialist signup)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.deps import normalize_phone
from app.models import Category, Consultant, Integration, User
from app.services.bookings import parse_fio


def user_has_consultant(db: Session, user_id: int) -> bool:
    return db.query(Consultant.id).filter(Consultant.user_id == user_id).first() is not None


def find_consultant_for_user(db: Session, user_id: int) -> Consultant | None:
    return db.query(Consultant).filter(Consultant.user_id == user_id).first()


def create_consultant_for_user(
    db: Session,
    user: User,
    *,
    fio: str,
    phone: str,
    email: str | None = None,
) -> Consultant:
    """
    Create Consultant + Integration stub if missing.
    Idempotent: returns existing Consultant when already present.
    """
    existing = find_consultant_for_user(db, user.id)
    if existing:
        return existing

    first_name, last_name, middle_name = parse_fio(fio)
    category = db.query(Category).filter(Category.name_category == "Общая").first()
    if not category:
        category = Category(name_category="Общая")
        db.add(category)
        db.flush()

    consultant_email = (email or user.email or "").strip() or f"user{user.id}@local.user"
    # Avoid unique email clash with another consultant
    clash = db.query(Consultant).filter(Consultant.email == consultant_email).first()
    if clash:
        consultant_email = f"user{user.id}.{consultant_email}"

    phone_n = normalize_phone(phone)
    consultant = Consultant(
        user_id=user.id,
        first_name=first_name or (user.first_name or ""),
        last_name=last_name or (user.last_name or ""),
        middle_name=middle_name or "",
        email=consultant_email[:254],
        phone=phone_n,
        telegram_nickname="",
        category_of_specialist_id=category.id,
    )
    db.add(consultant)
    db.flush()
    db.add(Integration(consultant_id=consultant.id))

    if first_name and not (user.first_name or "").strip():
        user.first_name = first_name
    if last_name and not (user.last_name or "").strip():
        user.last_name = last_name

    return consultant


def apply_user_names_from_fio(user: User, fio: str) -> None:
    first_name, last_name, _middle = parse_fio(fio)
    if first_name:
        user.first_name = first_name
    if last_name:
        user.last_name = last_name
