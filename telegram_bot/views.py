"""
Views для Telegram мини-приложения
"""
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from django.db.models import Count
from datetime import timedelta
from bookings.models import Service, TimeSlot, Appointment, Specialist, Calendar, UserProfile
from bookings.forms import AppointmentForm
import json

from telegram_bot.models import TelegramClient, TelegramClientSpecialist
from telegram_bot.utils import validate_telegram_webapp_init_data


def telegram_appointment(request):
    """
    Мини-приложение для записи на консультацию через Telegram
    """
    # Страница WebApp. Фильтрация по telegram_id делается через API (/telegram/api/me/).
    context = {
        'site_url': getattr(settings, "SITE_URL", "https://allyourclients.ru"),
    }
    
    return render(request, 'telegram_bot/appointment.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def telegram_appointment_create(request):
    """
    API endpoint для создания записи из Telegram мини-приложения
    """
    try:
        data = json.loads(request.body)

        init_data = data.get("init_data", "")
        telegram_user = None
        telegram_user_id = None
        telegram_username = ""
        if init_data:
            parsed = validate_telegram_webapp_init_data(init_data, getattr(settings, "TELEGRAM_BOT_TOKEN", ""))
            # user хранится строкой JSON в поле user
            if "user" in parsed:
                try:
                    telegram_user = json.loads(parsed["user"])
                    telegram_user_id = telegram_user.get("id")
                    telegram_username = telegram_user.get("username", "") or ""
                except Exception:
                    telegram_user = None
        
        # Получаем данные из запроса
        specialist_id = data.get('specialist_id')
        calendar_id = data.get('calendar_id')
        service_id = data.get('service_id')
        time_slot_id = data.get('time_slot_id')
        client_name = data.get('client_name')
        client_email = data.get('client_email')
        client_phone = data.get('client_phone', '')
        client_telegram = data.get('client_telegram', '')
        notes = data.get('notes', '')
        
        # Валидация
        if not all([service_id, time_slot_id, client_name, client_email, client_telegram]):
            return JsonResponse({
                'success': False,
                'error': 'Не все обязательные поля заполнены'
            }, status=400)
        
        # Получаем объекты
        try:
            service = Service.objects.select_related('calendar').get(id=service_id, is_active=True)
            if specialist_id and int(specialist_id) != service.specialist_id:
                return JsonResponse({'success': False, 'error': 'Услуга не принадлежит специалисту'}, status=400)
            if calendar_id and int(calendar_id) != service.calendar_id:
                return JsonResponse({'success': False, 'error': 'Услуга не принадлежит календарю'}, status=400)
            time_slot = TimeSlot.objects.get(id=time_slot_id, service=service, is_available=True, is_booked=False)
        except (Service.DoesNotExist, TimeSlot.DoesNotExist):
            return JsonResponse({
                'success': False,
                'error': 'Услуга или временной слот не найдены'
            }, status=404)

        calendar = service.calendar
        max_per_day = getattr(calendar, 'max_services_per_day', 0) or 0
        if max_per_day > 0:
            slot_date = time_slot.date
            existing_count = Appointment.objects.filter(
                calendar=service.calendar,
                appointment_date__date=slot_date,
                status__in=['pending', 'confirmed']
            ).count()
            if existing_count >= max_per_day:
                return JsonResponse({
                    'success': False,
                    'error': f'На эту дату достигнут лимит записей ({max_per_day} в день). Выберите другой день.'
                }, status=400)

        # Создаем запись
        appointment = Appointment.objects.create(
            specialist=service.specialist,
            service=service,
            calendar=service.calendar,
            time_slot=time_slot,
            appointment_date=timezone.make_aware(
                timezone.datetime.combine(time_slot.date, time_slot.start_time)
            ),
            duration=service.duration,
            status='pending',
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            client_telegram=client_telegram,
            notes=notes,
        )
        
        # Помечаем слот как занятый
        time_slot.is_booked = True
        time_slot.save()

        # Запоминаем связь telegram клиента со специалистом (если init_data валидный)
        if telegram_user_id:
            normalized_username = telegram_username.strip()
            try:
                client, _ = TelegramClient.objects.get_or_create(
                    telegram_id=telegram_user_id,
                    defaults={
                        "telegram_username": normalized_username,
                        "first_name": (telegram_user or {}).get("first_name", ""),
                        "last_name": (telegram_user or {}).get("last_name", ""),
                    },
                )
                client.telegram_username = normalized_username or client.telegram_username
                client.last_seen_at = timezone.now()
                client.last_specialist = service.specialist
                client.save()

                link, created_link = TelegramClientSpecialist.objects.get_or_create(
                    client=client,
                    specialist=service.specialist,
                    defaults={"first_booked_at": timezone.now(), "last_booked_at": timezone.now()},
                )
                if not created_link:
                    link.last_booked_at = timezone.now()
                    link.save()
            except Exception:
                pass
        
        # Отправляем уведомление в Telegram
        try:
            from .bot import send_appointment_notification
            send_appointment_notification(appointment)
        except Exception as e:
            # Логируем, но не прерываем процесс
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка отправки уведомления: {e}")
        
        return JsonResponse({
            'success': True,
            'appointment_id': appointment.id,
            'message': 'Запись успешно создана!'
        })
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Неверный формат данных'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def telegram_get_slots(request):
    """
    API endpoint для получения доступных слотов
    """
    service_id = request.GET.get('service_id')
    
    if not service_id:
        return JsonResponse({
            'success': False,
            'error': 'service_id обязателен'
        }, status=400)
    
    try:
        service = Service.objects.select_related('calendar').get(id=service_id, is_active=True)
    except Service.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Услуга не найдена'
        }, status=404)

    calendar = service.calendar
    book_ahead_hours = getattr(calendar, 'book_ahead_hours', 24) or 24
    max_services_per_day = getattr(calendar, 'max_services_per_day', 0) or 0
    now = timezone.now()
    min_slot_datetime = now + timedelta(hours=book_ahead_hours)

    time_slots = TimeSlot.objects.filter(
        service=service,
        is_available=True,
        is_booked=False,
        date__gte=now.date()
    ).order_by('date', 'start_time')

    slots_data = []
    for slot in time_slots:
        slot_datetime = timezone.make_aware(
            timezone.datetime.combine(slot.date, slot.start_time)
        )
        if slot_datetime < min_slot_datetime:
            continue
        if max_services_per_day > 0:
            appointments_that_day = Appointment.objects.filter(
                calendar=service.calendar,
                appointment_date__date=slot.date,
                status__in=['pending', 'confirmed']
            ).count()
            if appointments_that_day >= max_services_per_day:
                continue
        slots_data.append({
            'id': slot.id,
            'date': slot.date.isoformat(),
            'start_time': slot.start_time.strftime('%H:%M'),
            'end_time': slot.end_time.strftime('%H:%M'),
            'date_display': slot.date.strftime('%d.%m.%Y'),
        })
    
    return JsonResponse({
        'success': True,
        'service': {
            'id': service.id,
            'name': service.name,
            'duration': service.duration,
            'price': str(service.price) if service.price else None,
        },
        'slots': slots_data
    })


@csrf_exempt
@require_http_methods(["POST"])
def telegram_me(request):
    """
    Определить Telegram пользователя по initData и вернуть связанные данные.
    Возвращает:
    - linked_specialists: список специалистов, к которым клиент уже записывался
    - last_specialist_id
    """
    try:
        data = json.loads(request.body)
        init_data = data.get("init_data", "")
        parsed = validate_telegram_webapp_init_data(init_data, getattr(settings, "TELEGRAM_BOT_TOKEN", ""))

        user = None
        if "user" in parsed:
            user = json.loads(parsed["user"])
        if not user or "id" not in user:
            return JsonResponse({"success": False, "error": "Telegram user not found"}, status=400)

        telegram_id = int(user["id"])
        username = (user.get("username") or "").strip()

        client, _ = TelegramClient.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={
                "telegram_username": username,
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", ""),
            },
        )
        client.telegram_username = username or client.telegram_username
        client.last_seen_at = timezone.now()

        # Если раньше не было связей, попробуем найти последнюю запись по client_telegram == @username
        if not client.last_specialist and username:
            maybe = Appointment.objects.filter(client_telegram__iexact=f"@{username}").order_by("-appointment_date").first()
            if maybe:
                client.last_specialist = maybe.specialist
                TelegramClientSpecialist.objects.get_or_create(
                    client=client,
                    specialist=maybe.specialist,
                    defaults={"first_booked_at": timezone.now(), "last_booked_at": timezone.now()},
                )

        client.save()

        links = (
            TelegramClientSpecialist.objects.filter(client=client)
            .select_related("specialist", "specialist__user")
            .order_by("-last_booked_at")
        )
        linked = [
            {
                "id": l.specialist.id,
                "name": l.specialist.user.get_full_name() or l.specialist.user.username,
                "last_booked_at": l.last_booked_at.isoformat(),
            }
            for l in links
        ]

        return JsonResponse(
            {
                "success": True,
                "telegram_id": telegram_id,
                "telegram_username": username,
                "last_specialist_id": client.last_specialist_id,
                "linked_specialists": linked,
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@csrf_exempt
@require_http_methods(["GET"])
def telegram_specialist_calendars(request):
    specialist_id = request.GET.get("specialist_id")
    if not specialist_id:
        return JsonResponse({"success": False, "error": "specialist_id обязателен"}, status=400)

    calendars = Calendar.objects.filter(specialist_id=specialist_id, is_active=True).order_by("name")
    return JsonResponse(
        {
            "success": True,
            "calendars": [{"id": c.id, "name": c.name, "description": c.description} for c in calendars],
        }
    )


@csrf_exempt
@require_http_methods(["GET"])
def telegram_calendar_services(request):
    calendar_id = request.GET.get("calendar_id")
    if not calendar_id:
        return JsonResponse({"success": False, "error": "calendar_id обязателен"}, status=400)

    services = Service.objects.filter(calendar_id=calendar_id, is_active=True).select_related("specialist", "calendar").order_by("name")
    return JsonResponse(
        {
            "success": True,
            "services": [
                {
                    "id": s.id,
                    "name": s.name,
                    "specialist_id": s.specialist_id,
                    "calendar_id": s.calendar_id,
                }
                for s in services
            ],
        }
    )


def _get_specialist_by_init_data(init_data: str):
    """
    Специалист определяется по telegram_id, который хранится в UserProfile.telegram_id.
    """
    parsed = validate_telegram_webapp_init_data(init_data, getattr(settings, "TELEGRAM_BOT_TOKEN", ""))
    user = None
    if "user" in parsed:
        user = json.loads(parsed["user"])
    if not user or "id" not in user:
        raise ValueError("Telegram user not found")
    telegram_id = int(user["id"])
    profile = UserProfile.objects.filter(telegram_id=telegram_id, user_type="specialist").select_related("user").first()
    if not profile:
        raise ValueError("Вы не являетесь специалистом")
    specialist = getattr(profile.user, "specialist", None)
    if not specialist:
        raise ValueError("Профиль специалиста не найден")
    return specialist, telegram_id


def telegram_specialist_stats_page(request):
    return render(request, "telegram_bot/specialist_stats.html", {"site_url": getattr(settings, "SITE_URL", "https://allyourclients.ru")})


def telegram_specialist_upcoming_page(request):
    return render(request, "telegram_bot/specialist_upcoming.html", {"site_url": getattr(settings, "SITE_URL", "https://allyourclients.ru")})


@csrf_exempt
@require_http_methods(["POST"])
def telegram_specialist_stats_api(request):
    """
    Статистика специалиста (для мини-приложения).
    """
    try:
        data = json.loads(request.body)
        init_data = data.get("init_data", "")
        specialist, _ = _get_specialist_by_init_data(init_data)

        total = Appointment.objects.filter(specialist=specialist).count()
        by_status = (
            Appointment.objects.filter(specialist=specialist)
            .values("status")
            .annotate(cnt=Count("id"))
        )
        upcoming = Appointment.objects.filter(
            specialist=specialist,
            status__in=["pending", "confirmed"],
            appointment_date__gte=timezone.now(),
        ).count()

        return JsonResponse(
            {
                "success": True,
                "total_appointments": total,
                "upcoming_appointments": upcoming,
                "by_status": {row["status"]: row["cnt"] for row in by_status},
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def telegram_specialist_upcoming_api(request):
    """
    Ближайшие записи специалиста (для мини-приложения).
    """
    try:
        data = json.loads(request.body)
        init_data = data.get("init_data", "")
        specialist, _ = _get_specialist_by_init_data(init_data)

        items = (
            Appointment.objects.filter(
                specialist=specialist,
                status__in=["pending", "confirmed"],
                appointment_date__gte=timezone.now(),
            )
            .select_related("service", "calendar")
            .order_by("appointment_date")[:20]
        )
        result = []
        for a in items:
            result.append(
                {
                    "id": a.id,
                    "date": a.appointment_date.isoformat(),
                    "client_name": a.client_name,
                    "client_telegram": a.client_telegram,
                    "service_name": a.service.name if a.service else "",
                    "calendar_name": a.calendar.name if a.calendar else "",
                    "status": a.status,
                }
            )

        return JsonResponse({"success": True, "appointments": result})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

