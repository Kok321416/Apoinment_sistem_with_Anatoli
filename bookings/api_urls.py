"""
URL маршруты для API
"""
from django.urls import path
from . import api

urlpatterns = [
    path('calendars/<int:calendar_id>/events/', api.calendar_events, name='calendar_events_api'),
    path('specialist/calendars/', api.specialist_calendars_api, name='specialist_calendars_api'),
    path('telegram/webhook/', api.telegram_webhook, name='telegram_webhook'),
    path('user/appointments/', api.user_appointments_api, name='user_appointments_api'),
    path('telegram/link/', api.link_telegram, name='link_telegram'),
]

