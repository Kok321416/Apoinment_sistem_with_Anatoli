"""
URL маршруты для Telegram бота
"""
from django.urls import path
from . import views

urlpatterns = [
    path('appointment/', views.telegram_appointment, name='telegram_appointment'),
    path('appointment/create/', views.telegram_appointment_create, name='telegram_appointment_create'),
    path('api/slots/', views.telegram_get_slots, name='telegram_get_slots'),
]

