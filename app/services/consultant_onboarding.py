"""Create Consultant profile for an existing User (become specialist / specialist signup)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.deps import normalize_phone
from app.models import Category, Consultant, Integration, User
from app.services.bookings import parse_fio

_PLACEHOLDER_EMAIL_DOMAINS = ("telegram.user", "local.user")


def _looks_placeholder_email(email: str) -> bool:
    value = (email or "").strip().lower()
    if not value or "@" not in value:
        return True
    domain = value.rsplit("@", 1)[-1]
    return domain in _PLACEHOLDER_EMAIL_DOMAINS


def _email_candidates(user: User, email: str | None) -> list[str]:
    raw = (email or user.email or "").strip()
    out: list[str] = []
    if raw and not _looks_placeholder_email(raw):
        out.append(raw[:254])
    out.append(f"user{user.id}@local.user")
    out.append(f"user{user.id}.spec@local.user")
    if raw and _looks_placeholder_email(raw):
        prefixed = f"user{user.id}.{raw}"[:254]
        if prefixed not in out:
            out.append(prefixed)
    for i in range(2, 40):
        out.append(f"user{user.id}.{i}@local.user")
    seen: set[str] = set()
    unique: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def user_has_consultant(db: Session, user_id: int) -> bool:
    return db.query(Consultant.id).filter(Consultant.user_id == user_id).first() is not None


def find_consultant_for_user(db: Session, user_id: int) -> Consultant | None:
    return db.query(Consultant).filter(Consultant.user_id == user_id).first()


def _allocate_consultant_email_sync(db: Session, user: User, email: str | None) -> str:
    for candidate in _email_candidates(user, email):
        clash = db.query(Consultant).filter(Consultant.email == candidate).first()
        if not clash:
            return candidate
    return f"user{user.id}.{id(user) % 100000}@local.user"


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
    category = db.query(Category).filter(Category.code == "psychologist").first()
    if not category:
        category = db.query(Category).filter(Category.name_category == "Психолог").first()
    if not category:
        category = Category(name_category="Психолог", code="psychologist")
        db.add(category)
        db.flush()
    elif not getattr(category, "code", None) or category.code == "general":
        category.code = "psychologist"
        db.flush()

    consultant_email = _allocate_consultant_email_sync(db, user, email)
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


async def find_consultant_for_user_async(db, user_id: int) -> Consultant | None:
    from sqlalchemy import select

    return (
        await db.execute(select(Consultant).where(Consultant.user_id == user_id))
    ).scalar_one_or_none()


async def _allocate_consultant_email_async(db, user: User, email: str | None) -> str:
    from sqlalchemy import select

    for candidate in _email_candidates(user, email):
        clash = (
            await db.execute(select(Consultant).where(Consultant.email == candidate))
        ).scalar_one_or_none()
        if not clash:
            return candidate
    return f"user{user.id}.{id(user) % 100000}@local.user"


async def create_consultant_for_user_async(
    db,
    user: User,
    *,
    fio: str,
    phone: str,
    email: str | None = None,
) -> Consultant:
    existing = await find_consultant_for_user_async(db, user.id)
    if existing:
        return existing

    from sqlalchemy import select

    first_name, last_name, middle_name = parse_fio(fio)
    category = (
        await db.execute(select(Category).where(Category.code == "psychologist"))
    ).scalar_one_or_none()
    if not category:
        category = (
            await db.execute(select(Category).where(Category.name_category == "Психолог"))
        ).scalar_one_or_none()
    if not category:
        category = Category(name_category="Психолог", code="psychologist")
        db.add(category)
        await db.flush()
    elif not getattr(category, "code", None) or category.code == "general":
        category.code = "psychologist"
        await db.flush()

    consultant_email = await _allocate_consultant_email_async(db, user, email)
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
    await db.flush()
    db.add(Integration(consultant_id=consultant.id))

    if first_name and not (user.first_name or "").strip():
        user.first_name = first_name
    if last_name and not (user.last_name or "").strip():
        user.last_name = last_name

    return consultant
