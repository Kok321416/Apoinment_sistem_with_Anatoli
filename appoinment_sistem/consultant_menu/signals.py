"""
Сигналы для consultant_menu: создание Consultant при регистрации через соцсеть (Google/Telegram),
если в сессии сохранены ФИО и телефон со страницы регистрации.
"""
from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from consultant_menu.models import Consultant, Category


def _parse_fio(fio_str):
    parts = (fio_str or "").strip().split()
    last_name = parts[0] if parts else ""
    first_name = parts[1] if len(parts) > 1 else ""
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else ""
    return first_name, last_name, middle_name


@receiver(user_signed_up)
def create_consultant_on_social_signup(request, user, **kwargs):
    """После регистрации через Google/Telegram: если в сессии есть register_fio и register_phone — создаём Consultant."""
    if not getattr(request, "session", None):
        return
    fio = request.session.pop("register_fio", None)
    phone = request.session.pop("register_phone", None)
    if not fio or not phone:
        return
    if getattr(user, "consultant", None):
        return
    if not user.socialaccount_set.exists():
        return
    first_name, last_name, middle_name = _parse_fio(fio)
    category, _ = Category.objects.get_or_create(name_category="Общая")
    Consultant.objects.create(
        user=user,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        email=user.email or "",
        phone=phone,
        telegram_nickname="",
        category_of_specialist=category,
    )
