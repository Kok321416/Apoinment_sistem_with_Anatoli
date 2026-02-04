"""
Отправка напоминаний клиентам в Telegram о предстоящих консультациях.
Запуск: python manage.py send_booking_reminders (из appoinment_sistem).
Рекомендуется запускать по cron каждые 15–30 минут.
"""
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from consultant_menu.models import Booking
from consultant_menu.telegram_reminders import send_telegram_to_client, format_reminder_message


class Command(BaseCommand):
    help = 'Отправляет напоминания о консультациях клиентам в Telegram (за 24ч и за 1ч).'

    def handle(self, *args, **options):
        now = timezone.now()
        # Наивное время записи считаем в той же временной зоне, что и now
        if timezone.is_naive(now):
            tz = None
        else:
            tz = timezone.get_current_timezone()

        sent_24 = 0
        sent_1h = 0

        # Записи с привязанным Telegram, активные, в будущем
        qs = Booking.objects.filter(
            telegram_id__isnull=False,
            status__in=['pending', 'confirmed'],
            booking_date__gte=now.date(),
        ).select_related('service', 'calendar', 'calendar__consultant')

        for booking in qs:
            if not booking.booking_time:
                continue
            booking_dt = datetime.combine(booking.booking_date, booking.booking_time)
            if tz:
                booking_dt = timezone.make_aware(booking_dt, tz)
            delta = booking_dt - now
            delta_minutes = delta.total_seconds() / 60
            if delta_minutes <= 0:
                continue  # уже прошло

            # Напоминание за 24 часа (окно 23–25 ч)
            if not booking.reminder_24h_sent and 23 * 60 <= delta_minutes <= 25 * 60:
                text = format_reminder_message(booking, 24)
                if send_telegram_to_client(booking.telegram_id, text):
                    booking.reminder_24h_sent = True
                    booking.save(update_fields=['reminder_24h_sent'])
                    sent_24 += 1
                    self.stdout.write(f"  [24h] {booking.client_name} ({booking.booking_date} {booking.booking_time})")

            # Напоминание за 1 час (окно 50–70 мин)
            elif not booking.reminder_1h_sent and 50 <= delta_minutes <= 70:
                text = format_reminder_message(booking, 1)
                if send_telegram_to_client(booking.telegram_id, text):
                    booking.reminder_1h_sent = True
                    booking.save(update_fields=['reminder_1h_sent'])
                    sent_1h += 1
                    self.stdout.write(f"  [1h]  {booking.client_name} ({booking.booking_date} {booking.booking_time})")

        self.stdout.write(self.style.SUCCESS(f"Готово: отправлено 24h={sent_24}, 1h={sent_1h}"))
