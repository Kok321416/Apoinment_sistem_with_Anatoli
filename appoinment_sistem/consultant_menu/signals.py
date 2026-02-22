"""
Сигналы для consultant_menu: создание Consultant при регистрации через соцсеть (Google/Telegram),
уведомление специалисту в Telegram о новой записи, приветствие при входе через Telegram,
синхронизация Integration.telegram_chat_id при подключении/входе через Telegram OAuth (браузер),
синхронизация записей (Booking) с Google Calendar специалиста при создании/изменении/отмене.
"""
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added, social_account_updated
from consultant_menu.models import Consultant, Category, Booking, Integration


@receiver(user_logged_in)
def set_telegram_welcome_flag(request, user, **kwargs):
    """При входе через Telegram ставим флаг для показа приветственного сообщения."""
    if getattr(request, "session", None) and "telegram" in (request.path or ""):
        request.session["show_telegram_welcome"] = True


def _parse_fio(fio_str):
    parts = (fio_str or "").strip().split()
    last_name = parts[0] if parts else ""
    first_name = parts[1] if len(parts) > 1 else ""
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else ""
    return first_name, last_name, middle_name


def _sync_telegram_to_integration(user):
    """Если у пользователя есть Consultant и SocialAccount (Telegram) — записать uid в Integration для уведомлений."""
    if not user or not user.socialaccount_set.filter(provider="telegram").exists():
        return
    try:
        consultant = Consultant.objects.get(user=user)
    except Consultant.DoesNotExist:
        return
    sa = user.socialaccount_set.filter(provider="telegram").first()
    uid = getattr(sa, "uid", None)
    if uid is None:
        return
    integration, _ = Integration.objects.get_or_create(consultant=consultant)
    integration.telegram_chat_id = str(uid).strip()
    integration.telegram_connected = True
    integration.telegram_enabled = True
    integration.save(update_fields=["telegram_chat_id", "telegram_connected", "telegram_enabled"])


@receiver(social_account_added)
def sync_telegram_integration_on_connect(request, sociallogin, **kwargs):
    """После подключения соц. аккаунта (в т.ч. Telegram) в браузере — записать telegram uid в Integration и показать успех."""
    if getattr(sociallogin.account, "provider", None) != "telegram":
        return
    if getattr(request, "session", None):
        request.session["show_telegram_welcome"] = True
    user = getattr(sociallogin, "user", None)
    if user:
        _sync_telegram_to_integration(user)


@receiver(social_account_updated)
def sync_telegram_integration_on_update(request, sociallogin, **kwargs):
    """После обновления соц. аккаунта (повторный вход через Telegram) — обновить Integration."""
    if getattr(sociallogin.account, "provider", None) != "telegram":
        return
    user = getattr(sociallogin, "user", None)
    if user:
        _sync_telegram_to_integration(user)


@receiver(user_logged_in)
def sync_telegram_integration_on_login(request, user, **kwargs):
    """При входе через Telegram (path содержит telegram) — подтянуть chat_id из SocialAccount в Integration."""
    if getattr(request, "session", None) and "telegram" in (request.path or ""):
        _sync_telegram_to_integration(user)


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
    # Сразу привязать Telegram к Integration, если регистрация была через Telegram
    _sync_telegram_to_integration(user)


def _get_integration_for_booking(booking):
    """Возвращает Integration специалиста для записи или None."""
    consultant = None
    if getattr(booking, "calendar", None) and getattr(booking.calendar, "consultant", None):
        consultant = booking.calendar.consultant
    elif getattr(booking, "service", None) and getattr(booking.service, "consultant", None):
        consultant = booking.service.consultant
    if not consultant:
        return None
    integration, _ = Integration.objects.get_or_create(consultant=consultant)
    return integration


@receiver(post_save, sender=Booking)
def notify_on_new_booking(sender, instance, created, **kwargs):
    """При создании записи: уведомление специалисту в Telegram; клиенту — если telegram уже привязан."""
    if not created:
        return
    from consultant_menu.telegram_reminders import (
        notify_specialist_new_booking,
        send_telegram_to_client,
        format_client_booked_message,
    )
    notify_specialist_new_booking(instance)
    if getattr(instance, 'telegram_id', None):
        text = format_client_booked_message(instance)
        send_telegram_to_client(instance.telegram_id, text)


@receiver(post_save, sender=Booking)
def sync_booking_to_google_calendar(sender, instance, created, **kwargs):
    """
    При создании/обновлении/отмене записи — создать, обновить или удалить событие
    в Google Calendar специалиста (если он подключил календарь в интеграциях).
    """
    integration = _get_integration_for_booking(instance)
    if not integration or not getattr(integration, "google_calendar_connected", False):
        return
    if not (getattr(integration, "google_refresh_token", None) or "").strip():
        return
    from consultant_menu.google_calendar_sync import (
        create_booking_google_event,
        update_booking_google_event,
        delete_booking_google_event,
    )
    if instance.status == "cancelled":
        if getattr(instance, "google_event_id", None):
            delete_booking_google_event(integration, instance)
        return
    if created:
        create_booking_google_event(integration, instance)
    else:
        update_booking_google_event(integration, instance)


@receiver(post_delete, sender=Booking)
def delete_booking_from_google_calendar(sender, instance, **kwargs):
    """При удалении записи — удалить событие из Google Calendar специалиста (запись уже удалена из БД — не сохраняем)."""
    if not getattr(instance, "google_event_id", None):
        return
    integration = _get_integration_for_booking(instance)
    if not integration or not (getattr(integration, "google_refresh_token", None) or "").strip():
        return
    from consultant_menu.google_calendar_sync import delete_booking_google_event
    delete_booking_google_event(integration, instance, clear_event_id=False)