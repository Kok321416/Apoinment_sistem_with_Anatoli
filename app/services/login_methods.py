"""Helpers for counting available login methods (password, email, social)."""
from sqlalchemy.orm import Session

from app.models import EmailAddress, SocialAccount, User

SOCIAL_PROVIDERS = ("telegram", "yandex", "vk")


def count_other_login_methods(db: Session, user: User, *, exclude_provider: str | None = None) -> int:
    total = 0
    if user.has_usable_password:
        total += 1
    if db.query(EmailAddress).filter(
        EmailAddress.user_id == user.id,
        EmailAddress.verified.is_(True),
    ).first():
        total += 1
    for provider in SOCIAL_PROVIDERS:
        if provider == exclude_provider:
            continue
        if db.query(SocialAccount).filter(
            SocialAccount.user_id == user.id,
            SocialAccount.provider == provider,
        ).first():
            total += 1
    return total


def can_disconnect_social(db: Session, user: User, provider: str) -> tuple[bool, str]:
    linked = db.query(SocialAccount).filter(
        SocialAccount.user_id == user.id,
        SocialAccount.provider == provider,
    ).first()
    if not linked:
        labels = {"yandex": "Яндекс", "telegram": "Телеграм", "vk": "VK"}
        label = labels.get(provider, provider)
        return False, f"{label} не привязан."
    if count_other_login_methods(db, user, exclude_provider=provider) == 0:
        return False, "Нельзя отвязать: оставьте хотя бы один способ входа (почта, пароль или другой сервис)."
    return True, ""


async def count_other_login_methods_async(db, user: User, *, exclude_provider: str | None = None) -> int:
    from sqlalchemy import select

    total = 0
    if user.has_usable_password:
        total += 1
    verified = (
        await db.execute(
            select(EmailAddress.id).where(
                EmailAddress.user_id == user.id,
                EmailAddress.verified.is_(True),
            ).limit(1)
        )
    ).first()
    if verified:
        total += 1
    for provider in SOCIAL_PROVIDERS:
        if provider == exclude_provider:
            continue
        linked = (
            await db.execute(
                select(SocialAccount.id).where(
                    SocialAccount.user_id == user.id,
                    SocialAccount.provider == provider,
                ).limit(1)
            )
        ).first()
        if linked:
            total += 1
    return total


async def can_disconnect_social_async(db, user: User, provider: str) -> tuple[bool, str]:
    from sqlalchemy import select

    linked = (
        await db.execute(
            select(SocialAccount).where(
                SocialAccount.user_id == user.id,
                SocialAccount.provider == provider,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if not linked:
        labels = {"yandex": "Яндекс", "telegram": "Телеграм", "vk": "VK"}
        label = labels.get(provider, provider)
        return False, f"{label} не привязан."
    if await count_other_login_methods_async(db, user, exclude_provider=provider) == 0:
        return False, "Нельзя отвязать: оставьте хотя бы один способ входа (почта, пароль или другой сервис)."
    return True, ""
