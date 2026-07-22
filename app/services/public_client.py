"""Public specialist booking slug helpers and client gate session."""
from __future__ import annotations

import logging
import re
import secrets
import unicodedata

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Consultant

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:40] or "spec"


def specialist_slug_for(consultant: Consultant) -> str:
    """Stable public path segment. Prefer optional DB slug, else id-{id}."""
    return f"id-{consultant.id}"


def ensure_public_slug(db: Session, consultant: Consultant) -> str:
    """
    Return a public URL slug without requiring a mapped ORM column.
    Tries optional consultants.public_slug if the column exists; otherwise id-{id}.
    """
    stable = specialist_slug_for(consultant)
    try:
        row = db.execute(
            text("SELECT public_slug FROM consultants WHERE id = :id"),
            {"id": consultant.id},
        ).first()
    except Exception:
        db.rollback()
        return stable

    if row and row[0]:
        return str(row[0])

    base = _slugify(f"{consultant.first_name}-{consultant.last_name}") or f"spec-{consultant.id}"
    candidate = base
    n = 0
    while True:
        try:
            exists = db.execute(
                text("SELECT id FROM consultants WHERE public_slug = :slug LIMIT 1"),
                {"slug": candidate},
            ).first()
        except Exception:
            db.rollback()
            return stable
        if not exists:
            break
        n += 1
        candidate = f"{base}-{n}"

    try:
        db.execute(
            text("UPDATE consultants SET public_slug = :slug WHERE id = :id"),
            {"slug": candidate, "id": consultant.id},
        )
        db.commit()
        return candidate
    except Exception:
        db.rollback()
        logger.info("public_slug column unavailable; using %s", stable)
        return stable


def specialist_public_url(site_url: str, slug: str) -> str:
    return f"{site_url.rstrip('/')}/s/{slug}/"


def resolve_consultant_by_slug(db: Session, slug: str) -> Consultant | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    if slug.startswith("id-"):
        try:
            cid = int(slug.replace("id-", "", 1))
        except ValueError:
            cid = None
        if cid:
            found = db.query(Consultant).filter(Consultant.id == cid).first()
            if found:
                return found
    try:
        row = db.execute(
            text("SELECT id FROM consultants WHERE public_slug = :slug LIMIT 1"),
            {"slug": slug},
        ).first()
        if row:
            return db.query(Consultant).filter(Consultant.id == row[0]).first()
    except Exception:
        db.rollback()
    return None


def client_gate_ok(session: dict, consultant_id: int) -> bool:
    return (
        session.get("pc_consultant_id") == consultant_id
        and bool(session.get("pc_verified"))
        and bool((session.get("pc_name") or "").strip())
        and (
            bool((session.get("pc_email") or "").strip())
            or bool((session.get("pc_telegram") or "").strip())
        )
    )


def set_client_gate(
    session: dict,
    *,
    consultant_id: int,
    name: str,
    email: str = "",
    phone: str = "",
    telegram: str = "",
    verified: bool = False,
) -> None:
    session["pc_consultant_id"] = consultant_id
    session["pc_name"] = (name or "").strip()
    session["pc_email"] = (email or "").strip()
    session["pc_phone"] = (phone or "").strip()
    session["pc_telegram"] = (telegram or "").strip()
    session["pc_verified"] = bool(verified)


def clear_client_gate(session: dict) -> None:
    for key in (
        "pc_consultant_id",
        "pc_name",
        "pc_email",
        "pc_phone",
        "pc_telegram",
        "pc_verified",
        "pc_email_code",
        "pc_email_pending",
        "pc_email_code_at",
    ):
        session.pop(key, None)


def make_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def client_display_name(user) -> str:
    name = ""
    if hasattr(user, "get_full_name"):
        name = (user.get_full_name() or "").strip()
    if not name:
        first = (getattr(user, "first_name", None) or "").strip()
        last = (getattr(user, "last_name", None) or "").strip()
        name = f"{first} {last}".strip()
    if not name:
        name = (getattr(user, "username", None) or getattr(user, "email", None) or "Клиент").strip()
    return name


def apply_client_gate_from_user(db: Session, session: dict, *, consultant_id: int, user) -> None:
    """Open booking gate for a logged-in account (after register/login via specialist link)."""
    from app.models import SocialAccount

    name = client_display_name(user)
    email = (getattr(user, "email", None) or "").strip()
    phone = (session.get("register_phone") or session.get("pc_phone") or "").strip()
    telegram = (session.get("pc_telegram") or "").strip()

    user_id = getattr(user, "id", None)
    if user_id and not telegram:
        sa = (
            db.query(SocialAccount)
            .filter(SocialAccount.user_id == user_id, SocialAccount.provider == "telegram")
            .first()
        )
        if sa:
            telegram = (sa.uid or "").strip()
            try:
                import json

                extra = json.loads(sa.extra_data or "{}")
                username = (extra.get("username") or "").strip().lstrip("@")
                if username:
                    telegram = username
            except Exception:
                pass

    if not email and not telegram:
        telegram = f"user:{user_id or 'guest'}"

    set_client_gate(
        session,
        consultant_id=consultant_id,
        name=name,
        email=email,
        phone=phone,
        telegram=telegram,
        verified=True,
    )
