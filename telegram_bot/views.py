"""
Views для Telegram мини-приложения
"""
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from bookings.models import Service, TimeSlot, Appointment, Specialist
from bookings.forms import AppointmentForm
import json


def telegram_appointment(request):
    """
    Мини-приложение для записи на консультацию через Telegram
    """
    service_id = request.GET.get('service_id')
    service = None
    
    if service_id:
        try:
            service = Service.objects.get(id=service_id, is_active=True)
        except Service.DoesNotExist:
            pass
    
    # Получаем все активные услуги, если конкретная не выбрана
    if not service:
        services = Service.objects.filter(is_active=True).select_related('specialist', 'calendar')
    else:
        services = [service]
    
    # Получаем доступные слоты
    time_slots = TimeSlot.objects.filter(
        service__in=services,
        is_available=True,
        is_booked=False,
        date__gte=timezone.now().date()
    ).select_related('service', 'calendar').order_by('date', 'start_time')[:20]
    
    # Группируем слоты по услугам
    slots_by_service = {}
    for slot in time_slots:
        service_id = slot.service.id
        if service_id not in slots_by_service:
            slots_by_service[service_id] = {
                'service': slot.service,
                'slots': []
            }
        slots_by_service[service_id]['slots'].append(slot)
    
    context = {
        'services': services,
        'selected_service': service,
        'slots_by_service': slots_by_service,
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
        
        # Получаем данные из запроса
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
            service = Service.objects.get(id=service_id, is_active=True)
            time_slot = TimeSlot.objects.get(id=time_slot_id, service=service, is_available=True, is_booked=False)
        except (Service.DoesNotExist, TimeSlot.DoesNotExist):
            return JsonResponse({
                'success': False,
                'error': 'Услуга или временной слот не найдены'
            }, status=404)
        
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
        service = Service.objects.get(id=service_id, is_active=True)
    except Service.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Услуга не найдена'
        }, status=404)
    
    # Получаем доступные слоты
    time_slots = TimeSlot.objects.filter(
        service=service,
        is_available=True,
        is_booked=False,
        date__gte=timezone.now().date()
    ).order_by('date', 'start_time')
    
    slots_data = []
    for slot in time_slots:
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

