from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Специалист
    path('specialist/dashboard/', views.specialist_dashboard, name='specialist_dashboard'),
    path('specialist/link-telegram/', views.link_telegram_specialist, name='link_telegram_specialist'),
    path('specialist/calendar/', views.specialist_calendar, name='specialist_calendar'),
    path('specialist/appointments/', views.specialist_appointments, name='specialist_appointments'),
    path('specialist/calendars/', views.specialist_calendars, name='specialist_calendars'),
    path('specialist/calendars/create/', views.calendar_create, name='calendar_create'),
    path('specialist/calendars/<int:calendar_id>/', views.calendar_detail, name='calendar_detail'),
    path('specialist/calendars/<int:calendar_id>/edit/', views.calendar_edit, name='calendar_edit'),
    path('specialist/calendars/google/connect/', views.google_calendar_connect, name='google_calendar_connect'),
    path('specialist/calendars/google/callback/', views.google_calendar_callback, name='google_calendar_callback'),
    path('specialist/services/', views.specialist_services, name='specialist_services'),
    path('specialist/services/create/', views.service_create, name='service_create'),
    path('specialist/services/<int:service_id>/', views.service_detail, name='service_detail'),
    
    # Клиент
    path('client/appointments/', views.client_appointments, name='client_appointments'),
    
    # Запись на консультацию
    path('book/<str:invite_link>/', views.book_appointment, name='book_appointment'),
]


