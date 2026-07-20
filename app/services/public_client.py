"""Public specialist booking slug helpers and client gate session."""
from __future__ import annotations

import re
import secrets
import unicodedata

from sqlalchemy.orm import Session

from app.models import Consultant


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:40] or "spec"


def ensure_public_slug(db: Session, consultant: Consultant) -> str:
    if consultant.public_slug:
        return consultant.public_slug
    base = _slugify(f"{consultant.first_name}-{consultant.last_name}") or f"spec-{consultant.id}"
    candidate = base
    n = 0
    while db.query(Consultant).filter(Consultant.public_slug == candidate).first():
        n += 1
        candidate = f"{base}-{n}"
    consultant.public_slug = candidate
    db.add(consultant)
    db.commit()
    db.refresh(consultant)
    return consultant.public_slug


def specialist_public_url(site_url: str, slug: str) -> str:
    return f"{site_url.rstrip('/')}/s/{slug}/"


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
