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
from django.urls import path
from consultant_menu.views import (
    ConsultantAPIView, RegisterView, LoginView, LogoutView,
    home_view, calendars_view, services_view, clients_view, logout_view,
    register_view, login_view, calendar_view, public_booking_view, get_available_slots_api
)

urlpatterns = [
    # HTML страницы
    path("", home_view, name="home"),
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("calendars/", calendars_view, name="calendars"),
    path("services/", services_view, name="services"),
    path("clients/", clients_view, name="clients"),
    
    # API авторизация
    path('api/auth/register/', RegisterView.as_view(), name='api_register'),
    path('api/auth/login/', LoginView.as_view(), name='api_login'),
    path('api/auth/logout/', LogoutView.as_view(), name='api_logout'),
    
    # API
    path("consultant/consultant_list/", ConsultantAPIView.as_view()),
    
    # Админ панель
    path("admin/", admin.site.urls),

    # Календарь
    path("calendars/<int:calendar_id>/", calendar_view, name="calendar_detail"),
    
    # Публичная страница записи
    path("book/<int:calendar_id>/", public_booking_view, name="public_booking"),
    path("book/<int:calendar_id>/slots/", get_available_slots_api, name="get_available_slots"),
]


