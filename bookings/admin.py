from django.contrib import admin
from .models import UserProfile, Specialist, Calendar, Service, TimeSlot, Appointment


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'user_type', 'telegram_username', 'created_at']
    list_filter = ['user_type', 'created_at']
    search_fields = ['user__username', 'user__email', 'telegram_username']


@admin.register(Specialist)
class SpecialistAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization', 'invite_link', 'is_active', 'created_at']
    list_filter = ['specialization', 'is_active', 'created_at']
    search_fields = ['user__username', 'user__email', 'invite_link']


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ['name', 'specialist', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'specialist__user__username']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'specialist', 'calendar', 'duration', 'is_active', 'created_at']
    list_filter = ['is_active', 'calendar', 'created_at']
    search_fields = ['name', 'specialist__user__username', 'invite_link']


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['calendar', 'service', 'date', 'start_time', 'end_time', 'is_available', 'is_booked']
    list_filter = ['date', 'is_available', 'is_booked', 'calendar']
    search_fields = ['calendar__name', 'service__name']


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'service', 'specialist', 'appointment_date', 'status', 'created_at']
    list_filter = ['status', 'appointment_date', 'created_at', 'service']
    search_fields = ['client_name', 'client_email', 'service__name', 'specialist__user__username']


