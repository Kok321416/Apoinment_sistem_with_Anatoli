"""
URL маршруты для Telegram бота
"""
from django.urls import path
from . import views

urlpatterns = [
    path('appointment/', views.telegram_appointment, name='telegram_appointment'),
    path('appointment/create/', views.telegram_appointment_create, name='telegram_appointment_create'),
    path('api/slots/', views.telegram_get_slots, name='telegram_get_slots'),
    path('api/me/', views.telegram_me, name='telegram_me'),
    path('api/calendars/', views.telegram_specialist_calendars, name='telegram_specialist_calendars'),
    path('api/services/', views.telegram_calendar_services, name='telegram_calendar_services'),
    # Specialist mini-app
    path('specialist/stats/', views.telegram_specialist_stats_page, name='telegram_specialist_stats_page'),
    path('specialist/upcoming/', views.telegram_specialist_upcoming_page, name='telegram_specialist_upcoming_page'),
    path('api/specialist/stats/', views.telegram_specialist_stats_api, name='telegram_specialist_stats_api'),
    path('api/specialist/upcoming/', views.telegram_specialist_upcoming_api, name='telegram_specialist_upcoming_api'),
]

