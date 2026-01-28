"""
API endpoints для интеграции с внешними календарями (Google, Яндекс)
и для работы с Telegram ботом
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, date, time
from .models import Calendar, TimeSlot, Appointment, Specialist, Service, UserProfile
from django.contrib.auth.models import User


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def calendar_events(request, calendar_id):
    """
    Получить события календаря в формате для интеграции с Google/Яндекс календарями
    GET /api/calendars/{calendar_id}/events/
    """
    try:
        specialist = request.user.specialist
        calendar = get_object_or_404(Calendar, id=calendar_id, specialist=specialist)
        
        # Получаем временные слоты
        time_slots = TimeSlot.objects.filter(
            calendar=calendar,
            is_available=True
        ).order_by('date', 'start_time')
        
        # Получаем записи
        appointments = Appointment.objects.filter(
            calendar=calendar,
            status__in=['pending', 'confirmed']
        ).order_by('appointment_date')
        
        events = []
        
        # Добавляем временные слоты как события
        for slot in time_slots:
            slot_datetime = datetime.combine(slot.date, slot.start_time)
            end_datetime = datetime.combine(slot.date, slot.end_time)
            
            events.append({
                'id': f'slot_{slot.id}',
                'title': f'Доступный слот: {slot.start_time.strftime("%H:%M")} - {slot.end_time.strftime("%H:%M")}',
                'start': slot_datetime.isoformat(),
                'end': end_datetime.isoformat(),
                'type': 'time_slot',
                'available': not slot.is_booked,
            })
        
        # Добавляем записи как события
        for appointment in appointments:
            events.append({
                'id': f'appointment_{appointment.id}',
                'title': f'Консультация: {appointment.client_name}',
                'start': appointment.appointment_date.isoformat(),
                'end': (appointment.appointment_date + timezone.timedelta(minutes=appointment.duration)).isoformat(),
                'type': 'appointment',
                'status': appointment.status,
                'client_name': appointment.client_name,
                'client_email': appointment.client_email,
                'client_phone': appointment.client_phone,
                'client_telegram': appointment.client_telegram,
            })
        
        return Response({
            'calendar_id': calendar.id,
            'calendar_name': calendar.name,
            'events': events,
            'total_events': len(events)
        })
    
    except AttributeError:
        return Response(
            {'error': 'Вы не являетесь специалистом'},
            status=status.HTTP_403_FORBIDDEN
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def specialist_calendars_api(request):
    """
    Получить список календарей специалиста
    GET /api/specialist/calendars/
    """
    try:
        specialist = request.user.specialist
        calendars = Calendar.objects.filter(specialist=specialist, is_active=True)
        
        calendars_data = []
        for calendar in calendars:
            slots_count = TimeSlot.objects.filter(calendar=calendar).count()
            appointments_count = Appointment.objects.filter(calendar=calendar).count()
            
            calendars_data.append({
                'id': calendar.id,
                'name': calendar.name,
                'description': calendar.description,
                'color': calendar.color,
                'slots_count': slots_count,
                'appointments_count': appointments_count,
                'created_at': calendar.created_at.isoformat(),
            })
        
        return Response({
            'calendars': calendars_data,
            'total': len(calendars_data)
        })
    
    except AttributeError:
        return Response(
            {'error': 'Вы не являетесь специалистом'},
            status=status.HTTP_403_FORBIDDEN
        )


@api_view(['POST'])
def telegram_webhook(request):
    """
    Webhook для получения обновлений от Telegram бота
    POST /api/telegram/webhook/
    """
    from telegram_bot.bot import handle_telegram_update
    try:
        update_data = request.data
        handle_telegram_update(update_data)
        return Response({'status': 'ok'})
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_appointments_api(request):
    """
    Получить записи пользователя для Telegram бота
    GET /api/user/appointments/
    """
    user = request.user
    appointments = Appointment.objects.filter(client=user).order_by('-appointment_date')
    
    appointments_data = []
    for appointment in appointments:
        appointments_data.append({
            'id': appointment.id,
            'specialist_name': appointment.specialist.user.get_full_name(),
            'service_name': appointment.service.name if appointment.service else 'Консультация',
            'date': appointment.appointment_date.isoformat(),
            'duration': appointment.duration,
            'status': appointment.status,
            'status_display': appointment.get_status_display(),
            'notes': appointment.notes,
        })
    
    return Response({
        'appointments': appointments_data,
        'total': len(appointments_data)
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def link_telegram(request):
    """
    Привязать Telegram ID к пользователю
    POST /api/telegram/link/
    Body: {"telegram_id": 123456789}
    """
    telegram_id = request.data.get('telegram_id')
    if not telegram_id:
        return Response(
            {'error': 'telegram_id обязателен'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.telegram_id = telegram_id
        profile.save()
        
        return Response({
            'status': 'success',
            'message': 'Telegram успешно привязан',
            'telegram_id': profile.telegram_id
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

