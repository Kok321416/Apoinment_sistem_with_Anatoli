"""
Сигналы для синхронизации записей с Google Calendar.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Appointment
from .google_calendar import (
    create_google_calendar_event,
    update_google_calendar_event,
    delete_google_calendar_event,
    _delete_event_by_id,
)


@receiver(post_save, sender=Appointment)
def appointment_sync_google_calendar(sender, instance, created, **kwargs):
    """При создании/обновлении записи — создать или обновить событие в Google Calendar специалиста."""
    specialist = instance.specialist
    if not specialist.google_refresh_token:
        return
    if created:
        create_google_calendar_event(specialist, instance)
        return
    if instance.status == 'cancelled':
        if instance.google_event_id:
            delete_google_calendar_event(specialist, instance)
        return
    update_google_calendar_event(specialist, instance)


@receiver(post_delete, sender=Appointment)
def appointment_delete_google_calendar(sender, instance, **kwargs):
    """При удалении записи — удалить событие из Google Calendar (только API)."""
    if not instance.google_event_id:
        return
    specialist = instance.specialist
    if not specialist.google_refresh_token:
        return
    _delete_event_by_id(specialist, instance.google_event_id)
