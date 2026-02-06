"""
URL configuration for appoinment_sistem project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from consultant_menu.views import (
    ConsultantAPIView, RegisterView, LoginView, LogoutView,
    home_view, privacy_page_view, terms_page_view,
    calendars_view, services_view, logout_view,
    register_view, login_view, calendar_view, calendar_settings_edit, public_booking_view, get_available_slots_api, booking_view, profile_view,
    client_cards_list_view, client_card_detail_view,
    integrations_view, google_calendar_connect, google_calendar_callback,
    confirm_booking_telegram_api, connect_telegram_app, confirm_specialist_telegram_api,
    confirm_booking_telegram_browser, confirm_booking_telegram_browser_api,
    api_telegram_client_bookings,
    api_telegram_specialist_bookings,
)

urlpatterns = [
    # HTML страницы
    path("", home_view, name="home"),
    path("privacy/", privacy_page_view, name="privacy"),
    path("terms/", terms_page_view, name="terms"),
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("calendars/", calendars_view, name="calendars"),
    path("services/", services_view, name="services"),
    
    # API авторизация
    path('api/auth/register/', RegisterView.as_view(), name='api_register'),
    path('api/auth/login/', LoginView.as_view(), name='api_login'),
    path('api/auth/logout/', LogoutView.as_view(), name='api_logout'),
    
    # API
    path("consultant/consultant_list/", ConsultantAPIView.as_view()),
    
    # Админ панель
    path("admin/", admin.site.urls),
    # Вход через Google (django-allauth)
    path("accounts/", include("allauth.urls")),

    # Календарь
    path("calendars/<int:calendar_id>/", calendar_view, name="calendar_detail"),
    path("calendars/<int:calendar_id>/settings/", calendar_settings_edit, name="calendar_settings_edit"),
    
    # Публичная страница записи
    path("book/<int:calendar_id>/", public_booking_view, name="public_booking"),
    path("book/<int:calendar_id>/slots/", get_available_slots_api, name="get_available_slots"),
    path("api/booking/confirm-telegram/", confirm_booking_telegram_api, name="confirm_booking_telegram"),
    path("api/booking/confirm-telegram-browser/", confirm_booking_telegram_browser_api, name="confirm_booking_telegram_browser_api"),
    path("book/confirm-telegram/<str:link_token>/", confirm_booking_telegram_browser, name="confirm_booking_telegram_browser"),
    path("integrations/telegram/connect-app/", connect_telegram_app, name="connect_telegram_app"),
    path("api/specialist/connect-telegram/", confirm_specialist_telegram_api, name="confirm_specialist_telegram"),
    path("api/telegram/client-bookings/", api_telegram_client_bookings, name="api_telegram_client_bookings"),
    path("api/telegram/specialist-bookings/", api_telegram_specialist_bookings, name="api_telegram_specialist_bookings"),

    # Записи, карточки клиентов
    path("booking/", booking_view, name="booking"),
    path("clients/", client_cards_list_view, name="client_cards_list"),
    path("clients/<int:card_id>/", client_card_detail_view, name="client_card_detail"),

    # Профиль специалиста
    path("profile/", profile_view, name="profile"),
    
    # Интеграции
    path("integrations/", integrations_view, name="integrations"),
    path("integrations/google/connect/", google_calendar_connect, name="google_calendar_connect"),
    path("integrations/google/callback/", google_calendar_callback, name="google_calendar_callback"),

]

# Добавляем обработку медиа файлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


